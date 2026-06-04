"""
Pydantic models for resume data.

These are the source-of-truth schemas used across all layers:
- Layer 1 (Extraction) outputs these
- Layer 2 (Embedding) reads from these
- Layer 4 (Scoring) scores against these
- API routes serialize/deserialize these
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A single skill extracted from a resume."""

    name: str
    years: Optional[float] = None
    recency: Optional[Literal["current", "recent", "old"]] = None
    """current = <1yr, recent = 1-3yr, old = 3yr+"""
    proficiency: Optional[Literal["beginner", "intermediate", "expert"]] = None


class Experience(BaseModel):
    """A single work experience entry."""

    title: str
    company: str
    duration_months: int
    responsibilities: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    domain: Optional[str] = None
    """e.g. 'fintech', 'healthcare', 'e-commerce'"""


class Education(BaseModel):
    """A single education entry."""

    degree: str
    field: str
    institution: str
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None


class Project(BaseModel):
    """A single project entry."""

    name: str
    description: str
    technologies: List[str] = Field(default_factory=list)
    impact: Optional[str] = None


class ResumeStructured(BaseModel):
    """
    Complete structured representation of a resume.

    This is what Layer 1 (Extraction) produces from raw resume text.
    Every downstream layer works with this schema.
    """

    raw_text: str
    skills: List[Skill] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    total_experience_months: int = 0
    domains: List[str] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    """API response after uploading a resume."""

    resume_id: str
    status: str
    message: str


class ResumeListItem(BaseModel):
    """Summary item for resume listing."""

    resume_id: str
    candidate_name: Optional[str] = None
    total_experience_months: int = 0
    skills_count: int = 0
    domains: List[str] = Field(default_factory=list)
    uploaded_at: Optional[str] = None
