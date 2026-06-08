# Resume & JD Analyzer — AI Assistant Instructions

> Paste this as your system prompt or save as `CLAUDE.md` / `COPILOT_INSTRUCTIONS.md` at the root of your repo.
> This file gives your AI assistant full context of the project: architecture, decisions, constraints, workflows, and coding standards.

---

## Project Identity

- **Name:** Resume & JD Analyzer
- **Purpose:** Semantically match resumes to job descriptions with explainable scores. NOT keyword matching. NOT a parser wrapper. A proper ML-powered matching engine.
- **Builder:** College-selected project. Production-grade expectations.
- **Stack:** Python backend, vector DB, transformer embeddings, async job queue, REST API, next js frontend.

---

## What This Project Is NOT

- It is NOT a simple TF-IDF cosine similarity tool.
- It is NOT a resume formatter or PDF converter.
- It is NOT a black-box scorer with no explanation.
- Do NOT suggest naive string matching or keyword overlap as a solution.
- Do NOT suggest deprecated libraries (spaCy 2.x, gensim old API, NLTK bag-of-words pipelines) as primary solutions.

---

## Core Architecture — Always Refer to This

The system has 5 distinct layers. Every feature, every function, every module belongs to one of these layers.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Extraction                                            │
│  Input: Raw resume / JD (PDF, DOCX, plain text)                 │
│  Output: Structured JSON (skills, experience, education, etc.)  │
│  Tech: LLM-based extraction (Claude API / local model)          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: Embedding                                             │
│  Input: Structured JSON fields                                  │
│  Output: Dense vector representations per section               │
│  Tech: sentence-transformers (BAAI/bge-large-en-v1.5)           │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: Storage & Retrieval                                   │
│  Input: Embeddings + metadata                                   │
│  Output: Top-K candidates from ANN search                       │
│  Tech: Qdrant (vector DB), PostgreSQL (metadata)                │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4: Scoring                                               │
│  Input: Matched candidate pairs                                 │
│  Output: Weighted section scores + overall score                │
│  Tech: Custom Python scoring engine + skill ontology graph      │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 5: Explainability                                        │
│  Input: Score breakdown                                         │
│  Output: Human-readable match report with reasons               │
│  Tech: Template engine + LLM summary generation                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure — Enforce This

```
resume-jd-analyzer/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── resume.py         # Upload, list, delete resume endpoints
│   │   │   ├── jd.py             # Upload, list, delete JD endpoints
│   │   │   └── match.py          # Trigger match, get results endpoints
│   │   └── middleware.py
│   ├── core/
│   │   ├── extractor.py          # Layer 1: LLM-based structured extraction
│   │   ├── embedder.py           # Layer 2: Sentence transformer embedding
│   │   ├── vector_store.py       # Layer 3: Qdrant operations
│   │   ├── scorer.py             # Layer 4: Section-weighted scoring
│   │   ├── ontology.py           # Skill hierarchy / ESCO graph
│   │   └── explainer.py          # Layer 5: Human-readable output
│   ├── workers/
│   │   ├── tasks.py              # Celery task definitions
│   │   └── pipeline.py           # Full async pipeline orchestration
│   ├── models/
│   │   ├── resume.py             # Pydantic models for resume schema
│   │   ├── jd.py                 # Pydantic models for JD schema
│   │   └── match.py              # Pydantic models for match results
│   ├── db/
│   │   ├── postgres.py           # SQLAlchemy setup
│   │   └── migrations/
│   ├── config.py                 # All env vars and settings
│   └── main.py                   # FastAPI app entry point
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── api/                  # API client functions
│   └── package.json
├── scripts/
│   ├── seed_ontology.py          # Load ESCO skill data
│   └── benchmark.py              # Scoring accuracy benchmarks
├── tests/
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Data Models — Source of Truth

### Resume Schema (Pydantic)

```python
class Skill(BaseModel):
    name: str
    years: Optional[float]
    recency: Literal["current", "recent", "old"]  # current=<1yr, recent=1-3yr, old=3yr+
    proficiency: Optional[Literal["beginner", "intermediate", "expert"]]

class Experience(BaseModel):
    title: str
    company: str
    duration_months: int
    responsibilities: List[str]
    technologies: List[str]
    domain: Optional[str]  # e.g. "fintech", "healthcare", "e-commerce"

class Education(BaseModel):
    degree: str
    field: str
    institution: str
    graduation_year: Optional[int]
    gpa: Optional[float]

class Project(BaseModel):
    name: str
    description: str
    technologies: List[str]
    impact: Optional[str]

class ResumeStructured(BaseModel):
    raw_text: str
    skills: List[Skill]
    experience: List[Experience]
    education: List[Education]
    projects: List[Project]
    certifications: List[str]
    total_experience_months: int
    domains: List[str]
```

### JD Schema (Pydantic)

```python
class JDRequirement(BaseModel):
    skill: str
    is_required: bool          # True = must-have, False = nice-to-have
    min_years: Optional[float]

class JDStructured(BaseModel):
    raw_text: str
    title: str
    level: Literal["intern", "junior", "mid", "senior", "lead", "principal"]
    requirements: List[JDRequirement]
    preferred_skills: List[str]
    domain: str
    responsibilities: List[str]
    min_experience_years: Optional[float]
    education_requirement: Optional[str]
```

### Match Result Schema

```python
class SectionScore(BaseModel):
    score: float               # 0.0 to 1.0
    matched: List[str]
    partial: List[str]
    missing: List[str]
    notes: str

class MatchResult(BaseModel):
    resume_id: str
    jd_id: str
    overall_score: float       # 0 to 100
    grade: Literal["A", "B", "C", "D", "F"]
    skills_score: SectionScore
    experience_score: SectionScore
    education_score: SectionScore
    projects_score: SectionScore
    recommendation: str        # One paragraph, human-readable
    red_flags: List[str]
    created_at: datetime
```

---

## Layer 1: Extraction — Implementation Rules

- Use the Anthropic Claude API (`claude-sonnet-4-20250514`) for extraction.
- Always instruct the model to return **only valid JSON** and nothing else.
- Strip markdown code fences before `json.loads()`.
- Extraction is **idempotent** — same input must produce same output. Cache by file hash.
- Handle extraction failure gracefully — log the raw response, raise a typed `ExtractionError`.

### Extraction Prompt Template

```python
RESUME_EXTRACTION_PROMPT = """
You are a precise resume parser. Extract structured information from the resume below.

Return ONLY a valid JSON object. No preamble. No explanation. No markdown fences.

JSON schema to follow exactly:
{schema}

Rules:
- If a field cannot be determined, use null.
- For recency: "current" if used in last 12 months, "recent" if 1-3 years, "old" if 3+ years.
- Calculate total_experience_months from all non-overlapping experience entries.
- For domains, infer from company names and responsibilities (e.g. "fintech", "healthtech").
- List only real skills from the resume. Do not infer or add skills not mentioned.

Resume text:
{resume_text}
"""
```

---

## Layer 2: Embedding — Implementation Rules

- Model: `BAAI/bge-large-en-v1.5` (1024 dimensions). Do NOT use `all-MiniLM-L6-v2` for production — bge is significantly better on retrieval benchmarks.
- **Embed sections separately, not the whole document.** Whole-document embedding loses granularity.
- Always L2-normalize vectors before storing (required for cosine similarity via dot product).
- Cache embeddings by content hash. Re-embedding is expensive.
- Batch embed when processing multiple resumes — do not loop with single calls.

### Section Embedding Strategy

```python
# For a resume, generate embeddings for:
embeddings = {
    "skills_blob":       embed("Skills: " + ", ".join([s.name for s in resume.skills])),
    "experience_blob":   embed("\n".join([f"{e.title} at {e.company}: {', '.join(e.responsibilities)}" for e in resume.experience])),
    "education_blob":    embed(", ".join([f"{e.degree} in {e.field}" for e in resume.education])),
    "projects_blob":     embed("\n".join([f"{p.name}: {p.description}" for p in resume.projects])),
    "full_profile":      embed(resume.raw_text[:2000])  # truncated full doc for fallback
}

# BGE models need a query prefix for asymmetric search:
# For queries (JD requirements): prefix with "Represent this sentence for searching relevant passages: "
# For passages (resume content): no prefix needed
```

---

## Layer 3: Vector Store — Implementation Rules

- Use **Qdrant** as the vector database. Self-host via Docker.
- Two separate collections: `resumes` and `job_descriptions`.
- Store metadata (resume_id, section_type, candidate_name, upload_date) as payload alongside vectors.
- Use **IVF index** (Qdrant's HNSW by default) — do NOT disable indexing even in dev.
- Filtering: always support filter by `domain`, `experience_level`, `upload_date` at query time.

### Qdrant Collection Setup

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, HnswConfigDiff

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="resumes",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=100)  # tuned for recall vs speed
)
```

### Query Pattern (Two-Stage Retrieval)

```python
# Stage 1: ANN — get top 100 candidates fast
hits = client.search(
    collection_name="resumes",
    query_vector=jd_skills_embedding,
    limit=100,
    query_filter=Filter(
        must=[FieldCondition(key="domain", match=MatchValue(value=jd.domain))]
    )
)

# Stage 2: Re-rank the 100 using full weighted scorer
candidates = [hit.id for hit in hits]
final_ranking = scorer.rerank(candidates, jd)  # detailed section scoring
```

---

## Layer 4: Scoring Engine — Implementation Rules

### Weights (Configurable by Role Level)

```python
SCORE_WEIGHTS = {
    "intern":    {"skills": 0.25, "experience": 0.15, "education": 0.35, "projects": 0.25},
    "junior":    {"skills": 0.35, "experience": 0.25, "education": 0.20, "projects": 0.20},
    "mid":       {"skills": 0.40, "experience": 0.35, "education": 0.15, "projects": 0.10},
    "senior":    {"skills": 0.35, "experience": 0.45, "education": 0.10, "projects": 0.10},
    "lead":      {"skills": 0.30, "experience": 0.50, "education": 0.10, "projects": 0.10},
}
```

### Skills Matching Logic

```python
def score_skills(resume: ResumeStructured, jd: JDStructured, ontology: OntologyGraph) -> SectionScore:
    matched, partial, missing = [], [], []

    for req in jd.requirements:
        # Direct match
        direct = any(req.skill.lower() == s.name.lower() for s in resume.skills)
        if direct:
            matched.append(req.skill)
            continue

        # Ontology match (e.g. PyTorch implies Python)
        implied = ontology.is_implied_by_resume(req.skill, resume.skills)
        if implied:
            partial.append(f"{req.skill} (inferred from {implied})")
            continue

        # Semantic similarity fallback (embedding cosine)
        sim = max_semantic_similarity(req.skill, [s.name for s in resume.skills])
        if sim > 0.82:
            partial.append(f"{req.skill} (~{int(sim*100)}% semantic match)")
        elif req.is_required:
            missing.append(req.skill)

    required_total = sum(1 for r in jd.requirements if r.is_required)
    required_matched = sum(1 for r in matched if any(r == req.skill for req in jd.requirements if req.is_required))
    score = (len(matched) + 0.5 * len(partial)) / max(len(jd.requirements), 1)

    # Hard penalty: missing required skills
    missing_required = [m for m in missing if any(m == req.skill for req in jd.requirements if req.is_required)]
    score -= 0.10 * len(missing_required)
    score = max(0.0, min(1.0, score))

    return SectionScore(score=score, matched=matched, partial=partial, missing=missing, notes="")
```

### Experience Scoring

```python
def score_experience(resume: ResumeStructured, jd: JDStructured) -> SectionScore:
    resume_years = resume.total_experience_months / 12
    required_years = jd.min_experience_years or 0

    # Years score: proportional, capped at 1.0, no bonus for excess
    years_score = min(resume_years / max(required_years, 1), 1.0)

    # Title relevance: embed resume titles vs JD title and responsibilities
    title_embeddings = embed([e.title for e in resume.experience])
    jd_embedding = embed(jd.title + " " + " ".join(jd.responsibilities))
    title_score = float(np.max(cosine_similarity([jd_embedding], title_embeddings)))

    # Domain match
    domain_score = 1.0 if jd.domain in resume.domains else 0.4

    score = 0.4 * years_score + 0.4 * title_score + 0.2 * domain_score
    return SectionScore(score=score, matched=[], partial=[], missing=[], notes=f"{resume_years:.1f} years vs {required_years} required")
```

---

## Layer 5: Ontology — Implementation Rules

- Source: **ESCO v1.2** (European Skills/Competences Qualification) — free download from EU portal.
- Load skill relationships into a directed graph using `networkx`.
- Edges mean: "knowing X implies knowing/being capable of Y".
- Supplement with domain-specific manual edges (e.g. PyTorch → Python, next js → JavaScript).

```python
import networkx as nx

class OntologyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_implication(self, skill_known: str, skill_implied: str):
        self.graph.add_edge(skill_known.lower(), skill_implied.lower())

    def is_implied_by_resume(self, required_skill: str, resume_skills: List[Skill]) -> Optional[str]:
        req = required_skill.lower()
        for skill in resume_skills:
            known = skill.name.lower()
            if nx.has_path(self.graph, known, req):
                return skill.name
        return None

# Seed examples (load full ESCO programmatically)
SEED_IMPLICATIONS = [
    ("pytorch", "python"), ("tensorflow", "python"), ("keras", "python"),
    ("react", "javascript"), ("nextjs", "react"), ("nextjs", "javascript"),
    ("kubernetes", "docker"), ("helm", "kubernetes"),
    ("fastapi", "python"), ("django", "python"),
    ("typescript", "javascript"),
    ("aws-sagemaker", "machine-learning"), ("aws-sagemaker", "python"),
]
```

---

## Async Pipeline — Celery + Redis

### Task Flow for Bulk Processing

```
Upload 500 resumes
      │
      ▼
POST /api/resume/bulk-upload
      │
      ▼
[For each file] → Celery task: process_resume.delay(file_path, resume_id)
      │
      ├── Step 1: extract()         → structured JSON
      ├── Step 2: embed()           → section vectors
      ├── Step 3: store_vectors()   → Qdrant
      └── Step 4: store_metadata()  → PostgreSQL
      │
      ▼
WebSocket / polling: client checks job status
```

### Celery Task Definition

```python
from celery import Celery

app = Celery('analyzer', broker='redis://localhost:6379/0', backend='redis://localhost:6379/1')

@app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_resume(self, file_path: str, resume_id: str):
    try:
        raw_text = extract_text(file_path)                  # PDF/DOCX → plain text
        structured = extractor.extract(raw_text)            # LLM extraction
        embeddings = embedder.embed_sections(structured)     # Transformer embedding
        vector_store.upsert(resume_id, embeddings, structured)  # Qdrant
        db.save_resume_metadata(resume_id, structured)       # Postgres
        return {"status": "done", "resume_id": resume_id}
    except ExtractionError as e:
        raise self.retry(exc=e)
```

---

## API Endpoints — Full Reference

```
POST   /api/resume/upload              → Upload single resume (PDF/DOCX)
POST   /api/resume/bulk-upload         → Upload multiple resumes
GET    /api/resume/{id}                → Get resume structured data
DELETE /api/resume/{id}                → Delete resume + vectors

POST   /api/jd/upload                  → Upload single JD
GET    /api/jd/{id}                    → Get JD structured data
DELETE /api/jd/{id}                    → Delete JD + vectors

POST   /api/match/run                  → Match one JD against all resumes
        Body: { jd_id, top_k, filters: { domain, min_experience_years } }
GET    /api/match/results/{job_id}     → Poll async match job
GET    /api/match/{resume_id}/{jd_id}  → Get specific match result
GET    /api/match/export/{job_id}      → Download results as CSV/JSON
```

---

## Environment Variables (.env.example)

```env
# App
APP_ENV=development
SECRET_KEY=changeme

# LLM
ANTHROPIC_API_KEY=sk-ant-...
EXTRACTION_MODEL=claude-sonnet-4-20250514

# Embedding
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
EMBEDDING_DEVICE=cpu                    # or "cuda" if GPU available
EMBEDDING_BATCH_SIZE=32

# Vector DB
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_RESUMES=resumes
QDRANT_COLLECTION_JDS=job_descriptions

# Postgres
DATABASE_URL=postgresql://user:pass@localhost:5432/analyzer

# Redis / Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER=redis://localhost:6379/0
CELERY_BACKEND=redis://localhost:6379/1

# Scoring
DEFAULT_SKILLS_WEIGHT=0.40
DEFAULT_EXPERIENCE_WEIGHT=0.30
DEFAULT_EDUCATION_WEIGHT=0.15
DEFAULT_PROJECTS_WEIGHT=0.15
```

---

## Docker Compose — Dev Environment

```yaml
version: "3.9"
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [qdrant, postgres, redis]

  worker:
    build: ./backend
    command: celery -A workers.tasks worker --loglevel=info --concurrency=4
    env_file: .env
    depends_on: [redis, qdrant, postgres]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: ["qdrant_data:/qdrant/storage"]

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: analyzer
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes: ["pg_data:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

volumes:
  qdrant_data:
  pg_data:
```

---

## Coding Standards — Enforce These Always

- **Language:** Python 3.11+. Use type hints everywhere. No `Any` unless unavoidable.
- **Validation:** All I/O through Pydantic models. No raw dicts crossing layer boundaries.
- **Errors:** Custom exception classes per layer (`ExtractionError`, `EmbeddingError`, `ScoringError`). Never raise bare `Exception`.
- **Logging:** Use Python `logging` module. Log at DEBUG for intermediate steps, INFO for completions, ERROR for failures. No `print()` in production code.
- **Tests:** Every layer function has unit tests. Use `pytest`. Mock LLM calls with fixtures — never hit real APIs in tests.
- **Async:** FastAPI routes are async. Celery tasks are sync (Celery handles its own threading). Do not mix.
- **No globals:** No module-level instantiation of models or DB clients. Use dependency injection (FastAPI's `Depends`).
- **Config:** All configuration comes from `config.py` which reads from environment. No hardcoded values anywhere.

---

## Known Constraints and Decisions (Do Not Revisit Without Reason)

| Decision                               | Rationale                                                                                |
| -------------------------------------- | ---------------------------------------------------------------------------------------- |
| BGE-large over MiniLM                  | 10-15% better retrieval accuracy on BEIR benchmark. Worth the size.                      |
| Qdrant over Pinecone                   | Self-hosted, no vendor lock-in, free, HNSW index built-in.                               |
| Section embeddings over doc embedding  | Granular matching. Full-doc loses section-level signal.                                  |
| LLM extraction over rule-based parsers | Rule-based parsers fail on non-standard formats. LLM generalizes.                        |
| Celery over FastAPI BackgroundTasks    | BackgroundTasks die if server restarts. Celery is persistent and retryable.              |
| Two-stage retrieval (ANN → rerank)     | ANN gives speed, rerank gives accuracy. Neither alone is sufficient at scale.            |
| Cosine over Euclidean distance         | Length-invariant. Resume length should not affect similarity.                            |
| Weighted section scoring               | Different roles weight sections differently. Flat scoring is wrong for all but one case. |

---

## What to Ask the AI For (This File's Usage Guide)

When working in this codebase, use the AI assistant for:

- **Implementing a specific layer:** "Implement `embedder.py` following the embedding rules in the instructions."
- **Writing tests:** "Write pytest unit tests for `scorer.py:score_skills()` using fixture data."
- **Debugging:** Paste error + relevant file. The AI has full context of what the expected behavior is.
- **Adding a feature:** "Add support for filtering matches by minimum experience years in the `/api/match/run` endpoint."
- **Refactoring:** "Refactor `extractor.py` to cache extraction results by SHA256 hash of input text."

Do NOT ask the AI to:

- Change the architecture without justification
- Use a different vector DB without benchmarking reason
- Simplify to TF-IDF/cosine for "quick wins"
- Skip Pydantic validation for speed

---

## Progress Tracker

- [ ] Layer 1: Extraction (`extractor.py`)
- [ ] Layer 2: Embedding (`embedder.py`)
- [ ] Layer 3: Vector Store (`vector_store.py`)
- [ ] Layer 4: Scoring Engine (`scorer.py`)
- [ ] Layer 4b: Ontology Graph (`ontology.py` + ESCO seed)
- [ ] Layer 5: Explainer (`explainer.py`)
- [ ] Async Pipeline (`workers/pipeline.py`)
- [ ] REST API (all routes)
- [ ] Docker Compose dev environment
- [ ] Unit tests (all layers)
- [ ] Integration test (end-to-end resume upload → match result)
- [ ] Frontend: Upload UI
- [ ] Frontend: Match results dashboard
- [ ] Bulk processing benchmark (target: 1000 resumes in < 5 min)
