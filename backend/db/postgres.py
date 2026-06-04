"""
PostgreSQL database setup using SQLAlchemy async.

Defines:
- Async engine and session factory
- SQLAlchemy ORM models (tables)
- Dependency injection helpers for FastAPI
"""

import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

logger = logging.getLogger(__name__)


# ── Base ───────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


# ── ORM Models ────────────────────────────────────────────────
class ResumeRecord(Base):
    """Database record for a processed resume."""

    __tablename__ = "resumes"

    id = Column(String, primary_key=True)
    candidate_name = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    structured_data = Column(Text, nullable=False)  # JSON blob
    file_hash = Column(String(64), unique=True, nullable=False)
    total_experience_months = Column(Integer, default=0)
    domains = Column(Text, default="[]")  # JSON list
    skills_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def get_structured(self) -> dict:
        """Parse the stored JSON structured data."""
        return json.loads(self.structured_data)

    def get_domains(self) -> list:
        """Parse the stored JSON domains list."""
        return json.loads(self.domains)


class JDRecord(Base):
    """Database record for a processed job description."""

    __tablename__ = "job_descriptions"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    level = Column(String, nullable=False, default="mid")
    raw_text = Column(Text, nullable=False)
    structured_data = Column(Text, nullable=False)  # JSON blob
    file_hash = Column(String(64), unique=True, nullable=False)
    domain = Column(String, default="")
    requirements_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def get_structured(self) -> dict:
        """Parse the stored JSON structured data."""
        return json.loads(self.structured_data)


class MatchRecord(Base):
    """Database record for a match result."""

    __tablename__ = "match_results"

    id = Column(String, primary_key=True)
    resume_id = Column(String, nullable=False, index=True)
    jd_id = Column(String, nullable=False, index=True)
    overall_score = Column(Float, nullable=False)
    grade = Column(String(1), nullable=False)
    result_data = Column(Text, nullable=False)  # Full MatchResult as JSON
    job_id = Column(String, nullable=True, index=True)  # Async job ID
    created_at = Column(DateTime, default=func.now())

    def get_result(self) -> dict:
        """Parse the stored JSON match result."""
        return json.loads(self.result_data)


# ── Engine & Session Factory ──────────────────────────────────
_engine = None
_session_factory = None


def get_engine():
    """Get or create the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=(settings.app_env == "development"),
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory():
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.

    Usage:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables. Called during app startup."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def close_db() -> None:
    """Close the engine. Called during app shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    logger.info("Database connection closed")
