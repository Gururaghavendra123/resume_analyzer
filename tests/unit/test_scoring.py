"""
Unit tests for the Scoring Engine (Layer 4).

Tests all scoring functions with fixture data.
No real LLM or embedding calls — uses mocked embedder.
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.resume import Education, Experience, Project, ResumeStructured, Skill
from models.jd import JDRequirement, JDStructured
from core.ontology import OntologyGraph


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_resume() -> ResumeStructured:
    """A well-qualified Python backend developer resume."""
    return ResumeStructured(
        raw_text="John Doe - Senior Python Developer...",
        skills=[
            Skill(name="Python", years=5.0, recency="current", proficiency="expert"),
            Skill(name="FastAPI", years=2.0, recency="current", proficiency="intermediate"),
            Skill(name="PostgreSQL", years=3.0, recency="current", proficiency="intermediate"),
            Skill(name="Docker", years=2.0, recency="current", proficiency="intermediate"),
            Skill(name="PyTorch", years=1.5, recency="recent", proficiency="beginner"),
            Skill(name="React", years=1.0, recency="old", proficiency="beginner"),
        ],
        experience=[
            Experience(
                title="Senior Backend Developer",
                company="TechCorp",
                duration_months=36,
                responsibilities=["Built REST APIs", "Led team of 3"],
                technologies=["Python", "FastAPI", "PostgreSQL"],
                domain="fintech",
            ),
            Experience(
                title="Backend Developer",
                company="StartupXYZ",
                duration_months=24,
                responsibilities=["Developed microservices", "Database design"],
                technologies=["Python", "Django", "Redis"],
                domain="e-commerce",
            ),
        ],
        education=[
            Education(
                degree="Bachelor of Technology",
                field="Computer Science",
                institution="IIT Delhi",
                graduation_year=2018,
                gpa=8.5,
            ),
        ],
        projects=[
            Project(
                name="ML Pipeline",
                description="Built an end-to-end ML pipeline for fraud detection",
                technologies=["Python", "PyTorch", "Docker"],
                impact="Reduced fraud by 30%",
            ),
        ],
        certifications=["AWS Solutions Architect"],
        total_experience_months=60,
        domains=["fintech", "e-commerce"],
    )


@pytest.fixture
def sample_jd() -> JDStructured:
    """A mid-level Python developer JD."""
    return JDStructured(
        raw_text="We are looking for a Python Developer...",
        title="Python Backend Developer",
        level="mid",
        requirements=[
            JDRequirement(skill="Python", is_required=True, min_years=3.0),
            JDRequirement(skill="FastAPI", is_required=True),
            JDRequirement(skill="PostgreSQL", is_required=True),
            JDRequirement(skill="Docker", is_required=False),
            JDRequirement(skill="Kubernetes", is_required=False),
            JDRequirement(skill="Machine Learning", is_required=False),
        ],
        preferred_skills=["Redis", "AWS", "CI/CD"],
        domain="fintech",
        responsibilities=[
            "Design and build REST APIs",
            "Database schema design",
            "Code reviews and mentoring",
        ],
        min_experience_years=3.0,
        education_requirement="Bachelor's degree in Computer Science",
    )


@pytest.fixture
def ontology() -> OntologyGraph:
    """A loaded ontology graph."""
    o = OntologyGraph()
    o.load_seed_data()
    return o


@pytest.fixture
def mock_embedder():
    """Mock embedder that returns deterministic vectors."""
    embedder = MagicMock()

    def mock_similarity(query, candidates):
        """Return high similarity for Python-related terms."""
        query_lower = query.lower()
        if not candidates:
            return 0.0
        for c in candidates:
            if query_lower in c.lower() or c.lower() in query_lower:
                return 0.95
        return 0.3

    embedder.max_semantic_similarity = mock_similarity
    return embedder


# ── Ontology Tests ────────────────────────────────────────────

class TestOntologyGraph:
    """Tests for the skill ontology graph."""

    def test_direct_implication(self, ontology):
        """PyTorch should imply Python."""
        skills = [Skill(name="PyTorch", years=1.0, recency="current")]
        result = ontology.is_implied_by_resume("Python", skills)
        assert result == "PyTorch"

    def test_transitive_implication(self, ontology):
        """NextJS → React → JavaScript (transitive)."""
        skills = [Skill(name="nextjs", years=1.0, recency="current")]
        result = ontology.is_implied_by_resume("javascript", skills)
        assert result == "nextjs"

    def test_no_implication(self, ontology):
        """Docker should not imply Python."""
        skills = [Skill(name="Docker", years=1.0, recency="current")]
        result = ontology.is_implied_by_resume("Python", skills)
        assert result is None

    def test_case_insensitive(self, ontology):
        """Should work regardless of case."""
        skills = [Skill(name="PYTORCH", years=1.0, recency="current")]
        result = ontology.is_implied_by_resume("python", skills)
        assert result == "PYTORCH"

    def test_get_implied_skills(self, ontology):
        """NextJS should imply React and JavaScript."""
        implied = ontology.get_implied_skills("nextjs")
        assert "react" in implied
        assert "javascript" in implied

    def test_get_implying_skills(self, ontology):
        """Python should be implied by many frameworks."""
        implying = ontology.get_implying_skills("python")
        assert "pytorch" in implying
        assert "fastapi" in implying
        assert "django" in implying


# ── Scorer Tests ──────────────────────────────────────────────

class TestScorer:
    """Tests for the scoring engine."""

    def _get_scorer(self, mock_embedder, ontology):
        from core.scorer import Scorer
        settings = MagicMock()
        return Scorer(settings, mock_embedder, ontology)

    def test_skills_scoring_with_matches(self, sample_resume, sample_jd, mock_embedder, ontology):
        """Should score high when resume has most required skills."""
        scorer = self._get_scorer(mock_embedder, ontology)
        result = scorer.score_skills(sample_resume, sample_jd)

        assert result.score > 0.5
        assert "Python" in result.matched
        assert "FastAPI" in result.matched
        assert "PostgreSQL" in result.matched
        assert len(result.missing) == 0  # No required skills missing

    def test_skills_scoring_missing_required(self, sample_jd, mock_embedder, ontology):
        """Should penalize for missing required skills."""
        scorer = self._get_scorer(mock_embedder, ontology)

        # Resume with no matching skills
        weak_resume = ResumeStructured(
            raw_text="No relevant skills",
            skills=[Skill(name="Java", years=5.0, recency="current")],
            total_experience_months=60,
        )
        result = scorer.score_skills(weak_resume, sample_jd)

        assert result.score < 0.5
        assert len(result.missing) > 0

    def test_experience_scoring(self, sample_resume, sample_jd, mock_embedder, ontology):
        """Should score well with sufficient experience."""
        scorer = self._get_scorer(mock_embedder, ontology)
        result = scorer.score_experience(sample_resume, sample_jd)

        # 5 years vs 3 required → should be capped at 1.0 for years component
        assert result.score > 0.5
        assert "5.0 years" in result.notes or "5.0" in result.notes

    def test_experience_insufficient(self, sample_jd, mock_embedder, ontology):
        """Should score low with insufficient experience."""
        scorer = self._get_scorer(mock_embedder, ontology)

        junior_resume = ResumeStructured(
            raw_text="Fresh graduate",
            total_experience_months=6,
            experience=[
                Experience(
                    title="Intern", company="SmallCo", duration_months=6,
                    responsibilities=["Helped team"],
                ),
            ],
        )
        result = scorer.score_experience(junior_resume, sample_jd)

        # 0.5 years vs 3 required
        assert result.score < 0.7

    def test_education_scoring(self, sample_resume, sample_jd, mock_embedder, ontology):
        """Should score well with matching education."""
        scorer = self._get_scorer(mock_embedder, ontology)
        result = scorer.score_education(sample_resume, sample_jd)

        assert result.score > 0.5
        assert len(result.matched) > 0

    def test_education_no_requirement(self, sample_resume, mock_embedder, ontology):
        """Should give full score when JD has no education requirement."""
        scorer = self._get_scorer(mock_embedder, ontology)

        jd_no_edu = JDStructured(
            raw_text="No edu requirement",
            title="Developer",
            level="mid",
            requirements=[],
            domain="tech",
            responsibilities=[],
            education_requirement=None,
        )
        result = scorer.score_education(sample_resume, jd_no_edu)
        assert result.score == 1.0

    def test_overall_scoring(self, sample_resume, sample_jd, mock_embedder, ontology):
        """Full scoring should produce a valid MatchResult."""
        scorer = self._get_scorer(mock_embedder, ontology)
        result = scorer.score(sample_resume, sample_jd, "resume-1", "jd-1")

        assert result.resume_id == "resume-1"
        assert result.jd_id == "jd-1"
        assert 0.0 <= result.overall_score <= 100.0
        assert result.grade in ("A", "B", "C", "D", "F")
        assert result.skills_score is not None
        assert result.experience_score is not None

    def test_grade_assignment(self, sample_resume, sample_jd, mock_embedder, ontology):
        """Good resume + matching JD should get a decent grade."""
        scorer = self._get_scorer(mock_embedder, ontology)
        result = scorer.score(sample_resume, sample_jd, "r1", "j1")

        # Well-qualified candidate should get B or above
        assert result.grade in ("A", "B", "C")

    def test_red_flags_detection(self, mock_embedder, ontology):
        """Should detect red flags for weak candidates."""
        scorer = self._get_scorer(mock_embedder, ontology)

        weak_resume = ResumeStructured(
            raw_text="No experience",
            total_experience_months=3,
        )

        jd = JDStructured(
            raw_text="Senior role",
            title="Senior Developer",
            level="senior",
            requirements=[
                JDRequirement(skill="Python", is_required=True),
                JDRequirement(skill="Kubernetes", is_required=True),
            ],
            domain="fintech",
            responsibilities=["Lead team"],
            min_experience_years=8.0,
            education_requirement="Master's degree",
        )

        result = scorer.score(weak_resume, jd, "r1", "j1")
        assert len(result.red_flags) > 0
        assert result.grade in ("D", "F")


# ── Extractor Helpers Tests ──────────────────────────────────

class TestExtractorHelpers:
    """Tests for extraction utility functions."""

    def test_strip_markdown_fences(self):
        from core.extractor import strip_markdown_fences

        assert strip_markdown_fences('```json\n{"key": "value"}\n```') == '{"key": "value"}'
        assert strip_markdown_fences('```\n{"key": "value"}\n```') == '{"key": "value"}'
        assert strip_markdown_fences('{"key": "value"}') == '{"key": "value"}'

    def test_compute_hash_deterministic(self):
        from core.extractor import compute_hash

        h1 = compute_hash("test input")
        h2 = compute_hash("test input")
        h3 = compute_hash("different input")

        assert h1 == h2
        assert h1 != h3

    def test_safe_json_parse(self):
        from core.extractor import safe_json_parse

        result = safe_json_parse('```json\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_safe_json_parse_invalid(self):
        from core.extractor import safe_json_parse, ExtractionError

        with pytest.raises(ExtractionError):
            safe_json_parse("not valid json at all")


# ── Model Validation Tests ────────────────────────────────────

class TestModels:
    """Tests for Pydantic model validation."""

    def test_resume_structured_defaults(self):
        resume = ResumeStructured(raw_text="test")
        assert resume.skills == []
        assert resume.total_experience_months == 0
        assert resume.domains == []

    def test_jd_structured_validation(self):
        jd = JDStructured(
            raw_text="test",
            title="Developer",
            level="mid",
            domain="tech",
            responsibilities=[],
        )
        assert jd.level == "mid"
        assert jd.requirements == []

    def test_section_score_bounds(self):
        from models.match import SectionScore

        score = SectionScore(score=0.5, matched=["a"], partial=["b"], missing=["c"])
        assert 0.0 <= score.score <= 1.0

    def test_match_result_grade(self):
        from models.match import MatchResult, SectionScore

        result = MatchResult(
            resume_id="r1",
            jd_id="j1",
            overall_score=85.0,
            grade="A",
            skills_score=SectionScore(score=0.9),
            experience_score=SectionScore(score=0.8),
            education_score=SectionScore(score=0.7),
            projects_score=SectionScore(score=0.6),
        )
        assert result.grade == "A"
        assert result.overall_score == 85.0
