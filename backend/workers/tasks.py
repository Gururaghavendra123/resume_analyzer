"""
Celery task definitions for async processing.

Tasks:
- process_resume: Extract → Embed → Store (vectors + metadata)
- process_jd: Extract → Embed → Store (vectors + metadata)
- run_match_job: Retrieve → Score → Explain → Store results

All tasks are sync (Celery handles threading). Retry on failure.
"""

import os
import sys

# Ensure the backend/ directory is on sys.path so that
# 'core', 'db', 'models', 'config' are importable from Celery workers.
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import json
import logging
import uuid

# pyrefly: ignore [missing-import]
from celery import Celery
from sqlalchemy.orm import Session

from config import get_settings

logger = logging.getLogger(__name__)

# ── Celery App ─────────────────────────────────────────────────
settings = get_settings()
celery_app = Celery(
    "analyzer",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)


from celery.signals import worker_ready

@worker_ready.connect
def purge_queue(sender, **kwargs):
    """Purge the celery queue on worker startup to clear out stale tasks."""
    logger.info("Worker ready: Purging celery queue to prevent stale task replay...")
    sender.app.control.purge()


_components_cache = None
_db_engine = None


def _get_db_engine():
    global _db_engine
    if _db_engine is not None:
        return _db_engine
    
    import sys, os
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)
    
    from sqlalchemy import create_engine
    s = get_settings()
    sync_url = s.database_url.replace("+asyncpg", "+psycopg")
    _db_engine = create_engine(sync_url)
    return _db_engine


def _get_components():
    """
    Lazy-initialize all heavy components (embedder, extractor, etc.).
    Called inside tasks to avoid loading models at import time.
    Cached at the module level so they are loaded once per worker process.
    """
    global _components_cache
    if _components_cache is not None:
        return _components_cache

    import sys, os
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)

    from core.embedder import Embedder
    from core.explainer import Explainer
    from core.extractor import ResumeExtractor, JDExtractor
    from core.ontology import OntologyGraph
    from core.scorer import Scorer
    from core.vector_store import VectorStore

    s = get_settings()

    extractor_resume = ResumeExtractor(s)
    extractor_jd = JDExtractor(s)
    embedder = Embedder(s)
    vector_store = VectorStore(s)
    ontology = OntologyGraph()
    ontology.load_seed_data()
    scorer = Scorer(s, embedder, ontology)
    explainer = Explainer(s)

    _components_cache = {
        "extractor_resume": extractor_resume,
        "extractor_jd": extractor_jd,
        "embedder": embedder,
        "vector_store": vector_store,
        "ontology": ontology,
        "scorer": scorer,
        "explainer": explainer,
        "settings": s,
    }
    return _components_cache


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=30,  # 30s, 60s, 120s...
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_resume(self, file_path: str, resume_id: str):
    """
    Full resume processing pipeline:
    1. Extract text from file (PDF/DOCX/TXT)
    2. LLM extraction → structured JSON
    3. Generate section embeddings
    4. Store vectors in Qdrant
    5. Store metadata in PostgreSQL
    """
    logger.info("Processing resume '%s' from '%s'", resume_id, file_path)
    components = _get_components()

    # Step 1 + 2: Extract text and structure
    extractor = components["extractor_resume"]
    structured = extractor.extract_from_file(file_path)
    logger.info("Extraction complete for '%s': %d skills", resume_id, len(structured.skills))

    # Step 3: Generate embeddings
    embedder = components["embedder"]
    embeddings = embedder.embed_resume_sections(structured)
    logger.info("Embedding complete for '%s': %d sections", resume_id, len(embeddings))

    # Step 4: Store in Qdrant
    vector_store = components["vector_store"]
    vector_store.ensure_collections()
    metadata = {
        "candidate_name": "",  # Could be extracted from resume
        "domains": structured.domains,
        "total_experience_months": structured.total_experience_months,
    }
    vector_store.upsert_resume(resume_id, embeddings, metadata)

    # Step 5: Store in PostgreSQL (sync version using raw connection)
    _store_resume_metadata_sync(resume_id, structured, file_path)

    return {
        "status": "done",
        "resume_id": resume_id,
        "skills_count": len(structured.skills),
        "experience_count": len(structured.experience),
    }


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_jd(self, file_path: str, jd_id: str):
    """
    Full JD processing pipeline:
    1. Extract text from file
    2. LLM extraction → structured JSON
    3. Generate section embeddings
    4. Store vectors in Qdrant
    5. Store metadata in PostgreSQL
    """
    logger.info("Processing JD '%s' from '%s'", jd_id, file_path)
    components = _get_components()

    extractor = components["extractor_jd"]
    structured = extractor.extract_from_file(file_path)
    logger.info("JD extraction complete: '%s' [%s]", structured.title, structured.level)

    embedder = components["embedder"]
    embeddings = embedder.embed_jd_sections(structured)

    vector_store = components["vector_store"]
    vector_store.ensure_collections()
    metadata = {
        "title": structured.title,
        "domain": structured.domain,
        "level": structured.level,
    }
    vector_store.upsert_jd(jd_id, embeddings, metadata)

    _store_jd_metadata_sync(jd_id, structured, file_path)

    return {
        "status": "done",
        "jd_id": jd_id,
        "title": structured.title,
        "requirements_count": len(structured.requirements),
    }


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
)
def run_match_job(
    self,
    jd_id: str,
    top_k: int = 10,
    domain: str | None = None,
    min_experience_years: float | None = None,
):
    """
    Match a JD against all resumes:
    1. Load JD structured data
    2. ANN search in Qdrant (top 100)
    3. Re-rank with full scorer (top K)
    4. Generate explanations
    5. Store results
    """
    job_id = self.request.id or str(uuid.uuid4())
    logger.info("Running match job '%s' for JD '%s'", job_id, jd_id)

    components = _get_components()

    # Load JD data from DB
    jd_data = _load_jd_sync(jd_id)
    if not jd_data:
        return {"status": "error", "error": f"JD '{jd_id}' not found"}

    from models.jd import JDStructured
    jd = JDStructured.model_validate(jd_data)

    # Generate JD embeddings for search
    embedder = components["embedder"]
    jd_embeddings = embedder.embed_jd_sections(jd)

    # Use requirements embedding for search (or full_profile as fallback)
    search_vector = jd_embeddings.get("requirements_blob")
    if search_vector is None:
        search_vector = jd_embeddings.get("full_profile")
        
    if search_vector is None:
        return {"status": "error", "error": "Could not generate JD embedding"}

    # Stage 1: ANN search
    vector_store = components["vector_store"]
    min_exp_months = int(min_experience_years * 12) if min_experience_years else None
    candidates = vector_store.search_resumes(
        query_vector=search_vector,
        top_k=100,
        domain=domain,
        min_experience_months=min_exp_months,
    )

    logger.info("ANN search returned %d candidates", len(candidates))

    # Stage 2: Re-rank with full scorer
    scorer = components["scorer"]
    explainer = components["explainer"]
    results: list[dict] = []

    for candidate in candidates[:top_k * 2]:  # Score more than needed for safety
        resume_id = candidate["resume_id"]
        resume_data = _load_resume_sync(resume_id)
        if not resume_data:
            continue

        from models.resume import ResumeStructured
        resume = ResumeStructured.model_validate(resume_data)

        match_result = scorer.score(resume, jd, resume_id, jd_id)
        match_result = explainer.enrich_match_result(match_result)
        results.append(match_result.model_dump(mode="json"))

    # Sort by overall score, take top K
    results.sort(key=lambda x: x["overall_score"], reverse=True)
    results = results[:top_k]

    # Store results
    _store_match_results_sync(job_id, results)

    return {
        "status": "completed",
        "job_id": job_id,
        "jd_id": jd_id,
        "results_count": len(results),
    }


# ── Sync DB Helpers ────────────────────────────────────────────
# Celery tasks are sync, so we use synchronous DB operations.

def _store_resume_metadata_sync(
    resume_id: str, structured, file_path: str
) -> None:
    """Store resume metadata in PostgreSQL (sync for Celery)."""
    import hashlib
    from pathlib import Path

    from db.postgres import Base, ResumeRecord

    engine = _get_db_engine()
    Base.metadata.create_all(engine)

    file_content = Path(file_path).read_bytes()
    file_hash = hashlib.sha256(file_content).hexdigest()

    with Session(engine) as session:
        # Check by file_hash to avoid UniqueViolation if uploaded twice
        existing_by_hash = session.query(ResumeRecord).filter_by(file_hash=file_hash).first()
        if existing_by_hash and existing_by_hash.id != resume_id:
            logger.info("Resume with same hash already exists (ID: %s). Skipping insert.", existing_by_hash.id)
            return

        record = session.get(ResumeRecord, resume_id)
        if record:
            record.structured_data = structured.model_dump_json()
            record.total_experience_months = structured.total_experience_months
            record.domains = json.dumps(structured.domains)
            record.skills_count = len(structured.skills)
        else:
            record = ResumeRecord(
                id=resume_id,
                raw_text=structured.raw_text[:5000],
                structured_data=structured.model_dump_json(),
                file_hash=file_hash,
                total_experience_months=structured.total_experience_months,
                domains=json.dumps(structured.domains),
                skills_count=len(structured.skills),
            )
            session.add(record)
        session.commit()


def _store_jd_metadata_sync(jd_id: str, structured, file_path: str) -> None:
    """Store JD metadata in PostgreSQL (sync for Celery)."""
    import hashlib
    from pathlib import Path

    from db.postgres import Base, JDRecord

    engine = _get_db_engine()
    Base.metadata.create_all(engine)

    file_content = Path(file_path).read_bytes()
    file_hash = hashlib.sha256(file_content).hexdigest()

    with Session(engine) as session:
        # Check by file_hash to avoid UniqueViolation if uploaded twice
        existing_by_hash = session.query(JDRecord).filter_by(file_hash=file_hash).first()
        if existing_by_hash and existing_by_hash.id != jd_id:
            logger.info("JD with same hash already exists (ID: %s). Skipping insert.", existing_by_hash.id)
            return

        record = session.get(JDRecord, jd_id)
        if record:
            record.structured_data = structured.model_dump_json()
            record.domain = structured.domain
            record.requirements_count = len(structured.requirements)
        else:
            record = JDRecord(
                id=jd_id,
                title=structured.title,
                level=structured.level,
                raw_text=structured.raw_text[:5000],
                structured_data=structured.model_dump_json(),
                file_hash=file_hash,
                domain=structured.domain,
                requirements_count=len(structured.requirements),
            )
            session.add(record)
        session.commit()


def _load_resume_sync(resume_id: str) -> dict | None:
    """Load resume structured data from PostgreSQL (sync)."""
    from db.postgres import ResumeRecord

    engine = _get_db_engine()

    with Session(engine) as session:
        record = session.get(ResumeRecord, resume_id)
        if record:
            return record.get_structured()
    return None


def _load_jd_sync(jd_id: str) -> dict | None:
    """Load JD structured data from PostgreSQL (sync)."""
    from db.postgres import JDRecord

    engine = _get_db_engine()

    with Session(engine) as session:
        record = session.get(JDRecord, jd_id)
        if record:
            return record.get_structured()
    return None


def _store_match_results_sync(job_id: str, results: list[dict]) -> None:
    """Store match results in PostgreSQL (sync)."""
    from db.postgres import Base, MatchRecord

    engine = _get_db_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for result in results:
            record = MatchRecord(
                id=str(uuid.uuid4()),
                resume_id=result["resume_id"],
                jd_id=result["jd_id"],
                overall_score=result["overall_score"],
                grade=result["grade"],
                result_data=json.dumps(result),
                job_id=job_id,
            )
            session.add(record)
        session.commit()
