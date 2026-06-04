"""
Layer 2: Embedding Engine.

Uses sentence-transformers with BAAI/bge-large-en-v1.5 (1024 dimensions)
to generate dense vector representations per resume/JD section.

Key properties:
- Section-level embedding (not whole document) for granularity
- L2-normalization for cosine similarity via dot product
- BGE query prefix for asymmetric retrieval
- Batch embedding for efficiency
- Content-hash caching to avoid re-embedding
"""

import hashlib
import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from config import Settings
from core.exceptions import EmbeddingError
from models.jd import JDStructured
from models.resume import ResumeStructured

logger = logging.getLogger(__name__)

# BGE models require a query prefix for asymmetric retrieval
# Passages (resume content): no prefix needed
# Queries (JD requirements): prefix needed
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    """
    Generates section-level embeddings using sentence-transformers.

    Usage:
        embedder = Embedder(settings)
        vectors = embedder.embed_resume_sections(resume)
        # vectors is a dict of section_name → numpy array (1024-d)
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model: Optional[SentenceTransformer] = None
        self._cache: dict[str, np.ndarray] = {}

    def _get_model(self) -> SentenceTransformer:
        """Lazy-load the embedding model (avoids loading at import time)."""
        if self._model is None:
            logger.info(
                "Loading embedding model: %s (device: %s)",
                self._settings.embedding_model,
                self._settings.embedding_device,
            )
            # Force strictly CPU because of the meta tensor bug caused by missing CUDA dependencies
            self._model = SentenceTransformer(
                self._settings.embedding_model,
                device="cpu",
            )
            logger.info("Embedding model loaded successfully")
        return self._model

    def _content_hash(self, text: str) -> str:
        """SHA256 hash for caching."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str, is_query: bool = False) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: The text to embed.
            is_query: If True, prepend BGE query prefix (for JD/search queries).
                      If False, embed as passage (for resume content).

        Returns:
            L2-normalized 1024-d numpy array.
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        # Add query prefix for asymmetric search
        embed_text = f"{BGE_QUERY_PREFIX}{text}" if is_query else text

        # Check cache
        cache_key = self._content_hash(embed_text)
        if cache_key in self._cache:
            logger.debug("Embedding cache hit: %s", cache_key[:12])
            return self._cache[cache_key]

        try:
            model = self._get_model()
            vector = model.encode(
                embed_text,
                normalize_embeddings=True,  # L2-normalize
                show_progress_bar=False,
            )
            vector = np.array(vector, dtype=np.float32)
        except Exception as e:
            raise EmbeddingError(f"Embedding failed: {e}") from e

        # Cache and return
        self._cache[cache_key] = vector
        return vector

    def embed_batch(self, texts: list[str], is_query: bool = False) -> list[np.ndarray]:
        """
        Embed multiple texts in a batch for efficiency.

        Args:
            texts: List of texts to embed.
            is_query: If True, prepend BGE query prefix to each.

        Returns:
            List of L2-normalized 1024-d numpy arrays.
        """
        if not texts:
            return []

        # Add query prefix if needed
        embed_texts = [f"{BGE_QUERY_PREFIX}{t}" for t in texts] if is_query else texts

        # Check which are already cached
        results: list[Optional[np.ndarray]] = [None] * len(embed_texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(embed_texts):
            cache_key = self._content_hash(text)
            if cache_key in self._cache:
                results[i] = self._cache[cache_key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Batch encode uncached texts
        if uncached_texts:
            try:
                model = self._get_model()
                vectors = model.encode(
                    uncached_texts,
                    normalize_embeddings=True,
                    batch_size=self._settings.embedding_batch_size,
                    show_progress_bar=len(uncached_texts) > 10,
                )
            except Exception as e:
                raise EmbeddingError(f"Batch embedding failed: {e}") from e

            for idx, vec in zip(uncached_indices, vectors):
                vec_array = np.array(vec, dtype=np.float32)
                cache_key = self._content_hash(embed_texts[idx])
                self._cache[cache_key] = vec_array
                results[idx] = vec_array

        return results  # type: ignore[return-value]

    def embed_resume_sections(self, resume: ResumeStructured) -> dict[str, np.ndarray]:
        """
        Generate section-level embeddings for a resume.

        Returns a dict mapping section names to 1024-d vectors:
        - skills_blob: all skills concatenated
        - experience_blob: titles + responsibilities
        - education_blob: degree + field info
        - projects_blob: project names + descriptions
        - full_profile: truncated raw text fallback
        """
        sections: dict[str, str] = {}

        # Skills blob
        if resume.skills:
            sections["skills_blob"] = "Skills: " + ", ".join(
                s.name for s in resume.skills
            )

        # Experience blob
        if resume.experience:
            sections["experience_blob"] = "\n".join(
                f"{e.title} at {e.company}: {', '.join(e.responsibilities)}"
                for e in resume.experience
            )

        # Education blob
        if resume.education:
            sections["education_blob"] = ", ".join(
                f"{e.degree} in {e.field}" for e in resume.education
            )

        # Projects blob
        if resume.projects:
            sections["projects_blob"] = "\n".join(
                f"{p.name}: {p.description}" for p in resume.projects
            )

        # Full profile fallback (truncated)
        if resume.raw_text:
            sections["full_profile"] = resume.raw_text[:2000]

        # Embed all sections (as passages, no query prefix)
        embeddings: dict[str, np.ndarray] = {}
        for section_name, text in sections.items():
            try:
                embeddings[section_name] = self.embed(text, is_query=False)
                logger.debug(
                    "Embedded resume section '%s' (%d chars)",
                    section_name,
                    len(text),
                )
            except EmbeddingError as e:
                logger.warning("Failed to embed section '%s': %s", section_name, e)
                # Continue with other sections; don't fail the whole resume

        if not embeddings:
            raise EmbeddingError("No sections could be embedded for resume")

        return embeddings

    def embed_jd_sections(self, jd: JDStructured) -> dict[str, np.ndarray]:
        """
        Generate section-level embeddings for a job description.

        Uses query prefix since JD content is used for searching/matching.

        Returns:
        - requirements_blob: all required skills
        - responsibilities_blob: role responsibilities
        - full_profile: truncated raw text fallback
        """
        sections: dict[str, str] = {}

        # Requirements blob
        if jd.requirements:
            sections["requirements_blob"] = "Required skills: " + ", ".join(
                r.skill for r in jd.requirements
            )

        # Responsibilities blob
        if jd.responsibilities:
            sections["responsibilities_blob"] = "\n".join(jd.responsibilities)

        # Full profile
        if jd.raw_text:
            sections["full_profile"] = jd.raw_text[:2000]

        # Embed all sections (as queries for asymmetric retrieval)
        embeddings: dict[str, np.ndarray] = {}
        for section_name, text in sections.items():
            try:
                embeddings[section_name] = self.embed(text, is_query=True)
                logger.debug(
                    "Embedded JD section '%s' (%d chars)", section_name, len(text)
                )
            except EmbeddingError as e:
                logger.warning("Failed to embed JD section '%s': %s", section_name, e)

        if not embeddings:
            raise EmbeddingError("No sections could be embedded for JD")

        return embeddings

    def max_semantic_similarity(
        self, query: str, candidates: list[str]
    ) -> float:
        """
        Compute max cosine similarity between a query and candidate strings.
        Used by the scoring engine for fuzzy skill matching.
        """
        if not candidates:
            return 0.0

        query_vec = self.embed(query, is_query=True)
        candidate_vecs = self.embed_batch(candidates, is_query=False)

        similarities = [
            float(np.dot(query_vec, cv)) for cv in candidate_vecs
        ]
        return max(similarities) if similarities else 0.0
