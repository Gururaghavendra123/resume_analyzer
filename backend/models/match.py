"""
Pydantic models for match results.

These schemas define the output of the scoring engine (Layer 4)
and the explainability layer (Layer 5).
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SectionScore(BaseModel):
    """Score breakdown for a single resume section."""

    score: float = Field(ge=0.0, le=1.0, description="Section score from 0.0 to 1.0")
    matched: List[str] = Field(default_factory=list)
    partial: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    notes: str = ""


class MatchResult(BaseModel):
    """
    Complete match result between a resume and a job description.

    Produced by the scoring engine (Layer 4) and enriched by
    the explainability layer (Layer 5).
    """

    resume_id: str
    jd_id: str
    overall_score: float = Field(ge=0.0, le=100.0, description="Overall score 0-100")
    grade: Literal["A", "B", "C", "D", "F"]
    skills_score: SectionScore
    experience_score: SectionScore
    education_score: SectionScore
    projects_score: SectionScore
    recommendation: str = ""
    """One paragraph, human-readable recommendation."""
    red_flags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchRequest(BaseModel):
    """Request body for triggering a match job."""

    jd_id: str
    top_k: int = 10
    filters: Optional["MatchFilters"] = None


class MatchFilters(BaseModel):
    """Optional filters for match queries."""

    domain: Optional[str] = None
    min_experience_years: Optional[float] = None


class MatchJobStatus(BaseModel):
    """Status response for an async match job."""

    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: Optional[float] = None
    results: Optional[List[MatchResult]] = None
    error: Optional[str] = None


# Resolve forward reference
MatchRequest.model_rebuild()
