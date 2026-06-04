"""
Layer 3: Vector Store (Qdrant Operations).

Manages two Qdrant collections: 'resumes' and 'job_descriptions'.
Handles upsert, search, delete, and two-stage retrieval (ANN → rerank).

Key properties:
- HNSW index with tuned m=16, ef_construct=100
- Cosine distance (length-invariant)
- Metadata payload alongside vectors
- Filter support by domain, experience_level, upload_date
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import Settings
from core.exceptions import VectorStoreError

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Qdrant vector database wrapper.

    Manages storage and retrieval of resume/JD embeddings.

    Usage:
        vs = VectorStore(settings)
        vs.ensure_collections()
        vs.upsert_resume("resume-123", embeddings, metadata)
        hits = vs.search_resumes(query_vector, top_k=100, domain="fintech")
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[QdrantClient] = None

    def _get_client(self) -> QdrantClient:
        """Lazy-initialize Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(
                host=self._settings.qdrant_host,
                port=self._settings.qdrant_port,
            )
            logger.info(
                "Connected to Qdrant at %s:%d",
                self._settings.qdrant_host,
                self._settings.qdrant_port,
            )
        return self._client

    def ensure_collections(self) -> None:
        """
        Create Qdrant collections if they don't exist.
        Called during app startup.
        """
        client = self._get_client()
        collections = [
            self._settings.qdrant_collection_resumes,
            self._settings.qdrant_collection_jds,
        ]

        for collection_name in collections:
            try:
                client.get_collection(collection_name)
                logger.info("Collection '%s' already exists", collection_name)
            except (UnexpectedResponse, Exception):
                try:
                    client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=1024,  # BGE-large-en-v1.5 dimension
                            distance=Distance.COSINE,
                        ),
                        hnsw_config=HnswConfigDiff(
                            m=16,
                            ef_construct=100,
                        ),
                    )
                    logger.info("Created collection '%s'", collection_name)
                except Exception as e:
                    raise VectorStoreError(
                        f"Failed to create collection '{collection_name}': {e}",
                        collection=collection_name,
                    ) from e

    def upsert_resume(
        self,
        resume_id: str,
        embeddings: dict[str, np.ndarray],
        metadata: dict,
    ) -> list[str]:
        """
        Upsert resume section embeddings into Qdrant.

        Each section gets its own point with:
        - A unique point ID (uuid)
        - The section embedding vector
        - Metadata payload (resume_id, section_type, etc.)

        Returns list of inserted point IDs.
        """
        client = self._get_client()
        collection = self._settings.qdrant_collection_resumes
        point_ids: list[str] = []

        points: list[PointStruct] = []
        for section_name, vector in embeddings.items():
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)

            payload = {
                "resume_id": resume_id,
                "section_type": section_name,
                "candidate_name": metadata.get("candidate_name", ""),
                "domains": metadata.get("domains", []),
                "total_experience_months": metadata.get("total_experience_months", 0),
                "upload_date": datetime.utcnow().isoformat(),
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload=payload,
                )
            )

        try:
            client.upsert(collection_name=collection, points=points)
            logger.info(
                "Upserted %d vectors for resume '%s'", len(points), resume_id
            )
        except Exception as e:
            raise VectorStoreError(
                f"Failed to upsert resume vectors: {e}",
                collection=collection,
            ) from e

        return point_ids

    def upsert_jd(
        self,
        jd_id: str,
        embeddings: dict[str, np.ndarray],
        metadata: dict,
    ) -> list[str]:
        """Upsert JD section embeddings into Qdrant."""
        client = self._get_client()
        collection = self._settings.qdrant_collection_jds
        point_ids: list[str] = []

        points: list[PointStruct] = []
        for section_name, vector in embeddings.items():
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)

            payload = {
                "jd_id": jd_id,
                "section_type": section_name,
                "title": metadata.get("title", ""),
                "domain": metadata.get("domain", ""),
                "level": metadata.get("level", "mid"),
                "upload_date": datetime.utcnow().isoformat(),
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload=payload,
                )
            )

        try:
            client.upsert(collection_name=collection, points=points)
            logger.info("Upserted %d vectors for JD '%s'", len(points), jd_id)
        except Exception as e:
            raise VectorStoreError(
                f"Failed to upsert JD vectors: {e}",
                collection=collection,
            ) from e

        return point_ids

    def search_resumes(
        self,
        query_vector: np.ndarray,
        top_k: int = 100,
        domain: Optional[str] = None,
        min_experience_months: Optional[int] = None,
    ) -> list[dict]:
        """
        Stage 1: ANN search — get top-K resume candidates fast.

        Args:
            query_vector: The JD embedding to search with.
            top_k: Number of results to return.
            domain: Optional domain filter.
            min_experience_months: Optional minimum experience filter.

        Returns:
            List of dicts with resume_id, score, and metadata.
        """
        client = self._get_client()
        collection = self._settings.qdrant_collection_resumes

        # Build filter conditions
        must_conditions: list[FieldCondition] = []
        if domain:
            must_conditions.append(
                FieldCondition(key="domains", match=MatchValue(value=domain))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        try:
            hits = client.search(
                collection_name=collection,
                query_vector=query_vector.tolist(),
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as e:
            raise VectorStoreError(
                f"Resume search failed: {e}",
                collection=collection,
            ) from e

        # Deduplicate by resume_id (keep highest score per resume)
        seen: dict[str, dict] = {}
        for hit in hits:
            resume_id = hit.payload.get("resume_id", "")
            if resume_id not in seen or hit.score > seen[resume_id]["score"]:
                seen[resume_id] = {
                    "resume_id": resume_id,
                    "score": float(hit.score),
                    "section_type": hit.payload.get("section_type", ""),
                    "candidate_name": hit.payload.get("candidate_name", ""),
                    "domains": hit.payload.get("domains", []),
                    "total_experience_months": hit.payload.get(
                        "total_experience_months", 0
                    ),
                }

        # Apply experience filter post-search (Qdrant supports range, but simpler here)
        results = list(seen.values())
        if min_experience_months is not None:
            results = [
                r
                for r in results
                if r["total_experience_months"] >= min_experience_months
            ]

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            "ANN search returned %d unique resumes (top_k=%d)", len(results), top_k
        )
        return results

    def delete_resume(self, resume_id: str) -> None:
        """Delete all vectors associated with a resume_id."""
        client = self._get_client()
        collection = self._settings.qdrant_collection_resumes

        try:
            client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="resume_id", match=MatchValue(value=resume_id)
                        )
                    ]
                ),
            )
            logger.info("Deleted vectors for resume '%s'", resume_id)
        except Exception as e:
            raise VectorStoreError(
                f"Failed to delete resume vectors: {e}",
                collection=collection,
            ) from e

    def delete_jd(self, jd_id: str) -> None:
        """Delete all vectors associated with a jd_id."""
        client = self._get_client()
        collection = self._settings.qdrant_collection_jds

        try:
            client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="jd_id", match=MatchValue(value=jd_id))
                    ]
                ),
            )
            logger.info("Deleted vectors for JD '%s'", jd_id)
        except Exception as e:
            raise VectorStoreError(
                f"Failed to delete JD vectors: {e}",
                collection=collection,
            ) from e
