"""
End-to-End Validation Script.

Tests the core extraction → scoring pipeline WITHOUT needing
Celery, Redis, or Qdrant. Just Python + Gemini API key.

Usage:
    cd backend
    python scripts/validate_e2e.py

What it does:
    1. Extracts structured data from a hardcoded AI/ML resume
    2. Extracts structured data from a hardcoded GenAI JD
    3. Runs the scorer with debug logging
    4. Prints the full breakdown
"""

import os
import sys
import logging

# Ensure backend/ is on sys.path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Set up logging to see the scorer debug output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Test Data ──────────────────────────────────────────────────

TEST_RESUME_TEXT = """
RAHUL SHARMA
AI/ML Engineer | rahul.sharma@email.com | +91-9876543210

SUMMARY
Experienced AI Engineer with 3+ years building production ML systems and LLM-based applications.
Skilled in deep learning, NLP, and cloud deployments.

SKILLS
Python, PyTorch, TensorFlow, LangChain, RAG, FastAPI, Docker, Kubernetes,
PostgreSQL, Redis, Git, AWS, Hugging Face Transformers, Pandas, NumPy,
Scikit-learn, OpenCV, Streamlit, CI/CD, Linux

EXPERIENCE

AI Engineer | TechCorp AI Labs | Jan 2023 - Present (18 months)
- Built a RAG pipeline using LangChain + Qdrant for internal knowledge search
- Fine-tuned BERT models for document classification (95% accuracy)
- Deployed ML models on AWS ECS with Docker containers
- Implemented CI/CD pipeline using GitHub Actions

ML Engineer Intern | DataWorks Inc | Jun 2022 - Dec 2022 (7 months)
- Developed computer vision models for defect detection using PyTorch + YOLO
- Built data preprocessing pipelines with Pandas and NumPy
- Created dashboards with Streamlit for real-time model monitoring

EDUCATION
B.Tech in Computer Science | Indian Institute of Technology | 2022 | GPA: 8.7/10

PROJECTS
- LLM Chatbot: Built a conversational AI using LangChain, GPT API, and ChromaDB
- Image Classifier: Trained ResNet-50 on custom dataset, deployed on FastAPI
- Recommendation Engine: Collaborative filtering with Scikit-learn

CERTIFICATIONS
- AWS Certified Machine Learning Specialty
- Deep Learning Specialization (Coursera)
"""

TEST_JD_TEXT = """
GenAI Engineer - AI Platform Team

About the Role:
We are looking for a GenAI Engineer to join our AI Platform team. You will build
and maintain LLM-powered applications, RAG pipelines, and ML infrastructure.

Requirements:
- 2+ years experience in AI/ML engineering
- Strong proficiency in Python
- Experience with LLM frameworks (LangChain, LlamaIndex, or similar)
- Hands-on experience with RAG (Retrieval Augmented Generation)
- Experience with vector databases (Qdrant, Pinecone, ChromaDB, or FAISS)
- Familiarity with transformer models and Hugging Face
- Experience with Docker and containerized deployments
- Knowledge of SQL databases (PostgreSQL preferred)
- Git version control
- Good understanding of machine learning fundamentals

Preferred Skills:
- Experience with Kubernetes
- AWS or GCP cloud experience
- CI/CD pipelines
- FastAPI or Django for API development
- Experience with fine-tuning LLMs

Level: Mid
Domain: AI/ML
"""


def run_validation():
    """Run the full validation pipeline."""
    from config import get_settings

    settings = get_settings()

    if not settings.google_api_key:
        logger.error("GOOGLE_API_KEY is not set! Set it in your .env file.")
        sys.exit(1)

    # ── Step 1: Extract Resume ─────────────────────────────────
    logger.info("=" * 70)
    logger.info("STEP 1: Extracting Resume")
    logger.info("=" * 70)

    from core.extractor import ResumeExtractor
    resume_extractor = ResumeExtractor(settings)
    resume = resume_extractor.extract(TEST_RESUME_TEXT)

    logger.info("Extracted %d skills:", len(resume.skills))
    for i, skill in enumerate(resume.skills, 1):
        logger.info("  %2d. %-25s | years=%-4s | proficiency=%s",
                     i, skill.name, skill.years, skill.proficiency)

    logger.info("Extracted %d experiences, %d months total",
                 len(resume.experience), resume.total_experience_months)
    logger.info("Domains: %s", resume.domains)

    # ── Step 2: Extract JD ─────────────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("STEP 2: Extracting Job Description")
    logger.info("=" * 70)

    from core.extractor import JDExtractor
    jd_extractor = JDExtractor(settings)
    jd = jd_extractor.extract(TEST_JD_TEXT)

    logger.info("Title: %s | Level: %s | Domain: %s", jd.title, jd.level, jd.domain)
    logger.info("Extracted %d requirements:", len(jd.requirements))
    for i, req in enumerate(jd.requirements, 1):
        logger.info("  %2d. %-30s | required=%s | min_years=%s",
                     i, req.skill, req.is_required, req.min_years)

    logger.info("Preferred skills: %s", jd.preferred_skills)

    # ── Step 3: Initialize Scoring Components ──────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("STEP 3: Loading Embedder + Ontology + Scorer")
    logger.info("=" * 70)

    from core.embedder import Embedder
    from core.ontology import OntologyGraph
    from core.scorer import Scorer
    from core.explainer import Explainer

    embedder = Embedder(settings)
    ontology = OntologyGraph()
    ontology.load_seed_data()
    scorer = Scorer(settings, embedder, ontology)
    explainer = Explainer(settings)

    # ── Step 4: Run Scoring (this triggers the debug logs) ─────
    logger.info("")
    logger.info("=" * 70)
    logger.info("STEP 4: Running Scorer (debug logs below)")
    logger.info("=" * 70)

    result = scorer.score(resume, jd, "test-resume-001", "test-jd-001")

    # ── Step 5: Print Final Results ────────────────────────────
    logger.info("")
    logger.info("=" * 70)
    logger.info("STEP 5: FINAL RESULTS")
    logger.info("=" * 70)

    logger.info("Overall Score:    %.1f / 100", result.overall_score)
    logger.info("Grade:            %s", result.grade)
    logger.info("")
    logger.info("Section Breakdown:")
    logger.info("  Skills:      %.0f%% (weight varies by level)", result.skills_score.score * 100)
    logger.info("    Matched:   %s", ", ".join(result.skills_score.matched) or "None")
    logger.info("    Partial:   %s", ", ".join(result.skills_score.partial) or "None")
    logger.info("    Missing:   %s", ", ".join(result.skills_score.missing) or "None")
    logger.info("")
    logger.info("  Experience:  %.0f%%", result.experience_score.score * 100)
    logger.info("    Notes:     %s", result.experience_score.notes)
    logger.info("")
    logger.info("  Education:   %.0f%%", result.education_score.score * 100)
    logger.info("    Notes:     %s", result.education_score.notes)
    logger.info("")
    logger.info("  Projects:    %.0f%%", result.projects_score.score * 100)
    logger.info("    Notes:     %s", result.projects_score.notes)
    logger.info("")

    if result.red_flags:
        logger.info("Red Flags: %s", ", ".join(result.red_flags))
    else:
        logger.info("Red Flags: None")

    # Generate recommendation
    result = explainer.enrich_match_result(result)
    logger.info("")
    logger.info("Recommendation:")
    logger.info("  %s", result.recommendation)

    logger.info("")
    logger.info("=" * 70)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 70)

    # ── Sanity Check ───────────────────────────────────────────
    if result.skills_score.score == 0.0 and len(resume.skills) > 5:
        logger.warning("")
        logger.warning("⚠️  SKILLS SCORE IS 0%% WITH %d RESUME SKILLS — SOMETHING IS WRONG!",
                        len(resume.skills))
        logger.warning("Check the [SKILL MATCH] debug logs above to see what's happening.")
    elif result.overall_score < 40:
        logger.warning("")
        logger.warning("⚠️  OVERALL SCORE IS %.0f%% — this AI resume should score higher against an AI JD.",
                        result.overall_score)
        logger.warning("Review the section breakdowns above.")
    else:
        logger.info("")
        logger.info("✅ Scores look reasonable! The extraction and scoring pipeline is working.")


if __name__ == "__main__":
    run_validation()
