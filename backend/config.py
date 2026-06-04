"""
Application configuration.

All configuration is read from environment variables via pydantic-settings.
No hardcoded values anywhere — everything comes through here.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Resume & JD Analyzer."""

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],   # works from backend/ or root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    secret_key: str = "changeme-use-a-real-secret-in-production"
    upload_dir: str = "./uploads"

    # ── LLM — Google Gemini ────────────────────────────────────
    google_api_key: str = ""
    extraction_model: str = "gemini-2.0-flash"

    # ── Embedding ──────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # ── Vector DB — Qdrant ─────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_resumes: str = "resumes"
    qdrant_collection_jds: str = "job_descriptions"

    # ── PostgreSQL ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/analyzer"

    # ── Redis / Celery ─────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker: str = "redis://localhost:6379/0"
    celery_backend: str = "redis://localhost:6379/1"

    # ── Scoring Defaults ───────────────────────────────────────
    default_skills_weight: float = 0.40
    default_experience_weight: float = 0.30
    default_education_weight: float = 0.15
    default_projects_weight: float = 0.15
    explainer_use_llm: bool = False


def get_settings() -> Settings:
    """Factory function for dependency injection."""
    return Settings()
