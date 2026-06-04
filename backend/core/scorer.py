"""
Layer 4: Scoring Engine.

Computes weighted section scores between a resume and a job description.
Produces a MatchResult with section breakdowns, grade, and red flags.

Key features:
- Configurable weights by role level (intern → lead)
- Three-tier skill matching: direct → ontology → semantic
- Hard penalty for missing required skills
- Grade assignment (A/B/C/D/F)
- Red flag detection (experience gaps, missing must-haves, etc.)
"""

import logging
from typing import Optional

import numpy as np

from config import Settings
from core.embedder import Embedder
from core.exceptions import ScoringError
from core.ontology import OntologyGraph
from models.jd import JDStructured
from models.match import MatchResult, SectionScore
from models.resume import ResumeStructured

logger = logging.getLogger(__name__)


# ── Score Weights by Role Level ────────────────────────────────
SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "intern":    {"skills": 0.25, "experience": 0.15, "education": 0.35, "projects": 0.25},
    "junior":    {"skills": 0.35, "experience": 0.25, "education": 0.20, "projects": 0.20},
    "mid":       {"skills": 0.40, "experience": 0.35, "education": 0.15, "projects": 0.10},
    "senior":    {"skills": 0.35, "experience": 0.45, "education": 0.10, "projects": 0.10},
    "lead":      {"skills": 0.30, "experience": 0.50, "education": 0.10, "projects": 0.10},
    "principal": {"skills": 0.30, "experience": 0.50, "education": 0.10, "projects": 0.10},
}


def _assign_grade(score: float) -> str:
    """Assign a letter grade based on overall score (0-100)."""
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


class Scorer:
    """
    Computes match scores between a resume and a job description.

    Usage:
        scorer = Scorer(settings, embedder, ontology)
        result = scorer.score(resume, jd, resume_id, jd_id)
        # result is a MatchResult with section breakdowns
    """

    def __init__(
        self,
        settings: Settings,
        embedder: Embedder,
        ontology: OntologyGraph,
    ):
        self._settings = settings
        self._embedder = embedder
        self._ontology = ontology

    def score_skills(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
    ) -> SectionScore:
        """
        Score resume skills against JD requirements.

        Four-tier matching:
        1. Direct match (exact, case-insensitive)
        2. Substring / contains match (handles compound skills)
        3. Ontology match (e.g. PyTorch implies Python)
        4. Semantic similarity fallback (embedding cosine > 0.70)

        No additional penalty — the base score naturally reflects missing skills.
        """
        matched: list[str] = []
        partial: list[str] = []
        missing: list[str] = []

        resume_skill_names = [s.name.lower().strip() for s in resume.skills]

        for req in jd.requirements:
            req_lower = req.skill.lower().strip()

            # Tier 1: Direct match (exact, case-insensitive)
            direct = any(req_lower == s for s in resume_skill_names)
            if direct:
                matched.append(req.skill)
                continue

            # Tier 2: Substring / contains match
            # Catches cases like JD "LangGraph" matching resume "LangGraph/LangChain"
            # or resume "AWS" matching JD "Cloud & MLOps (AWS, GCP, Azure)"
            substring_match = any(
                req_lower in s or s in req_lower
                for s in resume_skill_names
            )
            if substring_match:
                matched.append(req.skill)
                continue

            # Tier 3: Ontology match
            implied = self._ontology.is_implied_by_resume(
                req.skill, resume.skills
            )
            if implied:
                partial.append(f"{req.skill} (inferred from {implied})")
                continue

            # Tier 4: Semantic similarity fallback (lowered threshold)
            try:
                sim = self._embedder.max_semantic_similarity(
                    req.skill, [s.name for s in resume.skills]
                )
                if sim > 0.70:
                    partial.append(f"{req.skill} (~{int(sim * 100)}% semantic match)")
                    continue
            except Exception:
                pass  # Embedding failure shouldn't block scoring

            # Not matched
            if req.is_required:
                missing.append(req.skill)

        # Calculate score — no additional penalty needed.
        # Missing skills are already reflected by not appearing in matched/partial.
        total_reqs = max(len(jd.requirements), 1)
        score = (len(matched) + 0.5 * len(partial)) / total_reqs
        score = max(0.0, min(1.0, score))

        notes_parts: list[str] = []
        if matched:
            notes_parts.append(f"{len(matched)} direct matches")
        if partial:
            notes_parts.append(f"{len(partial)} partial matches")
        if missing:
            notes_parts.append(f"{len(missing)} missing required")

        return SectionScore(
            score=score,
            matched=matched,
            partial=partial,
            missing=missing,
            notes=", ".join(notes_parts),
        )

    def score_experience(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
    ) -> SectionScore:
        """
        Score resume experience against JD requirements.

        Components:
        - Years score: proportional to required, capped at 1.0
        - Title relevance: semantic similarity of job titles
        - Domain match: bonus for matching domain
        """
        resume_years = resume.total_experience_months / 12
        required_years = jd.min_experience_years or 0

        # Years score
        years_score = min(resume_years / max(required_years, 1), 1.0)

        # Title relevance via embeddings
        title_score = 0.5  # default if no experience
        if resume.experience:
            try:
                resume_titles = [e.title for e in resume.experience]
                jd_query = f"{jd.title} {' '.join(jd.responsibilities[:3])}"
                title_sims = []
                for title in resume_titles:
                    sim = self._embedder.max_semantic_similarity(
                        jd_query, [title]
                    )
                    title_sims.append(sim)
                title_score = max(title_sims) if title_sims else 0.5
            except Exception:
                title_score = 0.5

        # Domain match
        domain_score = 1.0 if jd.domain.lower() in [d.lower() for d in resume.domains] else 0.4

        # Weighted combination
        score = 0.4 * years_score + 0.4 * title_score + 0.2 * domain_score

        matched: list[str] = []
        partial: list[str] = []
        missing: list[str] = []

        if resume_years >= required_years:
            matched.append(f"{resume_years:.1f} years experience")
        else:
            partial.append(f"{resume_years:.1f}/{required_years} years")

        if jd.domain.lower() in [d.lower() for d in resume.domains]:
            matched.append(f"Domain match: {jd.domain}")
        elif resume.domains:
            partial.append(f"Domain mismatch: has {', '.join(resume.domains)}, needs {jd.domain}")

        notes = f"{resume_years:.1f} years vs {required_years} required"

        return SectionScore(
            score=score,
            matched=matched,
            partial=partial,
            missing=missing,
            notes=notes,
        )

    def score_education(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
    ) -> SectionScore:
        """
        Score resume education against JD requirements.

        Considers:
        - Degree level matching
        - Field relevance (semantic similarity)
        """
        if not jd.education_requirement:
            # No education requirement → full score
            return SectionScore(
                score=1.0,
                matched=["No education requirement specified"],
                partial=[],
                missing=[],
                notes="JD has no education requirement",
            )

        matched: list[str] = []
        partial: list[str] = []
        missing: list[str] = []

        if not resume.education:
            return SectionScore(
                score=0.2,
                matched=[],
                partial=[],
                missing=[jd.education_requirement],
                notes="No education listed on resume",
            )

        # Check degree level
        degree_hierarchy = {
            "high school": 1, "diploma": 2, "associate": 3,
            "bachelor": 4, "bachelors": 4, "b.s.": 4, "b.a.": 4, "b.tech": 4, "b.e.": 4,
            "master": 5, "masters": 5, "m.s.": 5, "m.a.": 5, "m.tech": 5, "mba": 5,
            "phd": 6, "ph.d.": 6, "doctorate": 6,
        }

        best_degree_level = 0
        best_degree_name = ""
        for edu in resume.education:
            degree_lower = edu.degree.lower()
            for key, level in degree_hierarchy.items():
                if key in degree_lower and level > best_degree_level:
                    best_degree_level = level
                    best_degree_name = f"{edu.degree} in {edu.field}"

        # Match requirement
        req_lower = jd.education_requirement.lower()
        req_level = 0
        for key, level in degree_hierarchy.items():
            if key in req_lower:
                req_level = max(req_level, level)

        if best_degree_level >= req_level and req_level > 0:
            matched.append(best_degree_name)
            degree_score = 1.0
        elif best_degree_level > 0:
            partial.append(f"Has {best_degree_name}, needs {jd.education_requirement}")
            degree_score = 0.6
        else:
            missing.append(jd.education_requirement)
            degree_score = 0.2

        # Field relevance
        field_score = 0.5
        if resume.education:
            try:
                fields = [f"{e.degree} in {e.field}" for e in resume.education]
                field_score = self._embedder.max_semantic_similarity(
                    jd.education_requirement, fields
                )
            except Exception:
                field_score = 0.5

        score = 0.5 * degree_score + 0.5 * field_score
        notes = f"Best degree: {best_degree_name or 'none'}"

        return SectionScore(
            score=score,
            matched=matched,
            partial=partial,
            missing=missing,
            notes=notes,
        )

    def score_projects(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
    ) -> SectionScore:
        """
        Score resume projects against JD requirements.

        Evaluates:
        - Technology overlap with JD requirements
        - Semantic relevance of project descriptions to JD responsibilities
        """
        if not resume.projects:
            return SectionScore(
                score=0.1,
                matched=[],
                partial=[],
                missing=["No projects listed"],
                notes="No projects on resume",
            )

        matched: list[str] = []
        partial: list[str] = []

        # Technology overlap
        jd_skills = set(r.skill.lower() for r in jd.requirements)
        jd_preferred = set(s.lower() for s in jd.preferred_skills)
        all_jd_techs = jd_skills | jd_preferred

        for project in resume.projects:
            project_techs = set(t.lower() for t in project.technologies)
            overlap = project_techs & all_jd_techs

            if overlap:
                matched.append(
                    f"{project.name} (uses {', '.join(overlap)})"
                )
            else:
                partial.append(project.name)

        # Semantic relevance of project descriptions
        relevance_score = 0.5
        if resume.projects and jd.responsibilities:
            try:
                project_descs = [
                    f"{p.name}: {p.description}" for p in resume.projects
                ]
                jd_context = " ".join(jd.responsibilities[:5])
                relevance_score = self._embedder.max_semantic_similarity(
                    jd_context, project_descs
                )
            except Exception:
                relevance_score = 0.5

        # Combined score
        tech_score = len(matched) / max(len(resume.projects), 1)
        score = 0.5 * tech_score + 0.5 * relevance_score
        score = min(1.0, score)

        return SectionScore(
            score=score,
            matched=matched,
            partial=partial,
            missing=[],
            notes=f"{len(matched)}/{len(resume.projects)} projects relevant",
        )

    def detect_red_flags(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
        skills_score: SectionScore,
    ) -> list[str]:
        """Detect potential red flags in the match."""
        flags: list[str] = []

        # Missing required skills
        if skills_score.missing:
            flags.append(
                f"Missing {len(skills_score.missing)} required skill(s): "
                + ", ".join(skills_score.missing[:5])
            )

        # Significant experience gap
        resume_years = resume.total_experience_months / 12
        required_years = jd.min_experience_years or 0
        if required_years > 0 and resume_years < required_years * 0.5:
            flags.append(
                f"Significant experience gap: {resume_years:.1f} years "
                f"vs {required_years} required"
            )

        # No education when required
        if jd.education_requirement and not resume.education:
            flags.append("No education listed, but JD requires education")

        # Domain mismatch
        if jd.domain and jd.domain.lower() not in [
            d.lower() for d in resume.domains
        ]:
            flags.append(
                f"Domain mismatch: JD needs '{jd.domain}', "
                f"resume has {resume.domains or ['none']}"
            )

        # Very low skills score
        if skills_score.score < 0.2:
            flags.append("Very low skills alignment (<20%)")

        return flags

    def score(
        self,
        resume: ResumeStructured,
        jd: JDStructured,
        resume_id: str,
        jd_id: str,
    ) -> MatchResult:
        """
        Compute full match result between a resume and JD.

        Returns a MatchResult with:
        - Section scores (skills, experience, education, projects)
        - Weighted overall score (0-100)
        - Letter grade (A-F)
        - Red flags
        """
        try:
            # Score each section
            skills = self.score_skills(resume, jd)
            experience = self.score_experience(resume, jd)
            education = self.score_education(resume, jd)
            projects = self.score_projects(resume, jd)

            # Get weights for this role level
            level = jd.level if jd.level in SCORE_WEIGHTS else "mid"
            weights = SCORE_WEIGHTS[level]

            # Weighted overall score
            overall = (
                weights["skills"] * skills.score
                + weights["experience"] * experience.score
                + weights["education"] * education.score
                + weights["projects"] * projects.score
            ) * 100

            overall = max(0.0, min(100.0, overall))
            grade = _assign_grade(overall)

            # Red flags
            red_flags = self.detect_red_flags(resume, jd, skills)

            return MatchResult(
                resume_id=resume_id,
                jd_id=jd_id,
                overall_score=round(overall, 1),
                grade=grade,
                skills_score=skills,
                experience_score=experience,
                education_score=education,
                projects_score=projects,
                recommendation="",  # Filled by explainer
                red_flags=red_flags,
            )

        except Exception as e:
            raise ScoringError(
                f"Scoring failed: {e}",
                resume_id=resume_id,
                jd_id=jd_id,
            ) from e
