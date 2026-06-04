"""
Pydantic models for Job Description data.

Source-of-truth schemas for JD extraction, storage, and matching.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class JDRequirement(BaseModel):
    """A single skill requirement from a job description."""

    skill: str
    is_required: bool = True
    """True = must-have, False = nice-to-have"""
    min_years: Optional[float] = None


class JDStructured(BaseModel):
    """
    Complete structured representation of a job description.

    Produced by Layer 1 (Extraction) from raw JD text.
    Used by Layer 4 (Scoring) to match against resumes.
    """

    raw_text: str
    title: str
    level: Optional[Literal["intern", "junior", "mid", "senior", "lead", "principal"]] = None
    requirements: List[JDRequirement] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    domain: str = ""
    responsibilities: List[str] = Field(default_factory=list)
    min_experience_years: Optional[float] = None
    education_requirement: Optional[str] = None


class JDUploadResponse(BaseModel):
    """API response after uploading a job description."""

    jd_id: str
    status: str
    message: str


class JDListItem(BaseModel):
    """Summary item for JD listing."""

    jd_id: str
    title: str
    level: str
    domain: str
    requirements_count: int = 0
    uploaded_at: Optional[str] = None
