"""
Layer 1: Extraction Engine.

Uses Google Gemini API to extract structured data from raw resume/JD text.
Outputs validated Pydantic models (ResumeStructured, JDStructured).

Key properties:
- Idempotent: same input → same output (cached by SHA256 hash)
- Validates output against Pydantic schemas
- Strips markdown code fences before JSON parsing
- Handles PDF/DOCX → plaintext conversion
- Custom ExtractionError on any failure
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import google.generativeai as genai
import pdfplumber
from docx import Document as DocxDocument

from config import Settings
from core.exceptions import DocumentParseError, ExtractionError
from models.jd import JDStructured
from models.resume import ResumeStructured

logger = logging.getLogger(__name__)


# ── Extraction Prompts ─────────────────────────────────────────

RESUME_EXTRACTION_PROMPT = """You are a precise resume parser. Extract structured information from the resume below.

Return ONLY a valid JSON object. No preamble. No explanation. No markdown fences.

JSON schema to follow exactly:
{schema}

Rules:
- If a field cannot be determined, use null.
- For recency: "current" if used in last 12 months, "recent" if 1-3 years, "old" if 3+ years.
- Calculate total_experience_months from all non-overlapping experience entries.
- For domains, infer from company names and responsibilities (e.g. "fintech", "healthtech").
- CRITICAL: Extract ATOMIC, single-concept skills (e.g. "Python", "Docker", "LangChain"). DO NOT extract long sentences or comma-separated lists as a single skill. Break them down!
- For proficiency, infer from context: years of usage, project complexity, certifications.

Resume text:
{resume_text}"""


JD_EXTRACTION_PROMPT = """You are a precise job description parser. Extract structured information from the JD below.

Return ONLY a valid JSON object. No preamble. No explanation. No markdown fences.

JSON schema to follow exactly:
{schema}

Rules:
- If a field cannot be determined, use null.
- For level, infer from title and requirements: "intern", "junior", "mid", "senior", "lead", "principal".
- is_required=true for must-have skills, false for nice-to-have/preferred.
- CRITICAL: Extract ATOMIC, single-concept skills (e.g. "Python", "Docker", "LangChain"). DO NOT extract long sentences, bullet points, or grouped lists (like "Cloud (AWS, GCP)") as a single skill. Break them down into "AWS", "GCP", etc!
- preferred_skills is a separate list of bonus/nice-to-have skills.
- For domain, infer from company context and responsibilities (e.g. "fintech", "healthcare").
- min_experience_years: extract the minimum years required, or null if not specified.

JD text:
{jd_text}"""


# ── Schema Definitions for Prompts ─────────────────────────────

RESUME_SCHEMA = """{
    "raw_text": "string (leave empty, will be set programmatically)",
    "skills": [{"name": "string", "years": "float or null", "recency": "current|recent|old", "proficiency": "beginner|intermediate|expert or null"}],
    "experience": [{"title": "string", "company": "string", "duration_months": "int", "responsibilities": ["string"], "technologies": ["string"], "domain": "string or null"}],
    "education": [{"degree": "string", "field": "string", "institution": "string", "graduation_year": "int or null", "gpa": "float or null"}],
    "projects": [{"name": "string", "description": "string", "technologies": ["string"], "impact": "string or null"}],
    "certifications": ["string"],
    "total_experience_months": "int",
    "domains": ["string"]
}"""

JD_SCHEMA = """{
    "raw_text": "string (leave empty, will be set programmatically)",
    "title": "string",
    "level": "intern|junior|mid|senior|lead|principal",
    "requirements": [{"skill": "string", "is_required": "bool", "min_years": "float or null"}],
    "preferred_skills": ["string"],
    "domain": "string",
    "responsibilities": ["string"],
    "min_experience_years": "float or null",
    "education_requirement": "string or null"
}"""


# ── Text Extraction from Files ─────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """Extract plaintext from a PDF file using pdfplumber."""
    try:
        text_parts: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        if not text_parts:
            raise DocumentParseError("No text extracted from PDF", file_path)
        return "\n\n".join(text_parts)
    except DocumentParseError:
        raise
    except Exception as e:
        raise DocumentParseError(f"Failed to parse PDF: {e}", file_path) from e


def extract_text_from_docx(file_path: str) -> str:
    """Extract plaintext from a DOCX file using python-docx."""
    try:
        doc = DocxDocument(file_path)
        text_parts = [para.text for para in doc.paragraphs if para.text.strip()]
        if not text_parts:
            raise DocumentParseError("No text extracted from DOCX", file_path)
        return "\n\n".join(text_parts)
    except DocumentParseError:
        raise
    except Exception as e:
        raise DocumentParseError(f"Failed to parse DOCX: {e}", file_path) from e


def extract_text_from_file(file_path: str) -> str:
    """
    Extract plaintext from a file based on its extension.
    Supports: .pdf, .docx, .txt
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    elif suffix == ".docx":
        return extract_text_from_docx(file_path)
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8")
    else:
        raise DocumentParseError(
            f"Unsupported file type: {suffix}. Supported: .pdf, .docx, .txt",
            file_path,
        )


# ── JSON Parsing Helpers ──────────────────────────────────────

def strip_markdown_fences(text: str) -> str:
    """
    Strip markdown code fences from LLM output.
    Handles ```json ... ``` and ``` ... ``` patterns.
    """
    text = text.strip()
    # Remove opening fence (with optional language tag)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    # Remove closing fence
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def safe_json_parse(raw: str) -> dict:
    """
    Parse JSON from LLM output, stripping markdown fences first.
    Raises ExtractionError with the raw response on failure.
    """
    cleaned = strip_markdown_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s\nRaw response:\n%s", e, raw[:500])
        raise ExtractionError(
            f"LLM returned invalid JSON: {e}",
            raw_response=raw,
        ) from e


# ── Content Hashing ────────────────────────────────────────────

def compute_hash(text: str) -> str:
    """SHA256 hash of input text for idempotent caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Extractor Classes ─────────────────────────────────────────

class ResumeExtractor:
    """
    Extracts structured resume data from raw text using Google Gemini.

    Usage:
        extractor = ResumeExtractor(settings)
        result = extractor.extract(raw_text)
        # result is a validated ResumeStructured instance
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache: dict[str, ResumeStructured] = {}
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            settings.extraction_model,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=8192,
            )
        )

    def extract(self, raw_text: str) -> ResumeStructured:
        """
        Extract structured data from resume text.
        Idempotent — cached by SHA256 hash of input.
        """
        text_hash = compute_hash(raw_text)

        # Cache hit
        if text_hash in self._cache:
            logger.debug("Resume extraction cache hit: %s", text_hash[:12])
            return self._cache[text_hash]

        # Build prompt
        prompt = RESUME_EXTRACTION_PROMPT.format(
            schema=RESUME_SCHEMA,
            resume_text=raw_text[:8000],  # Truncate very long resumes
        )

        # Call Gemini
        try:
            logger.info("Extracting resume with %s", self._settings.extraction_model)
            response = self._model.generate_content(prompt)
            raw_response = response.text
        except Exception as e:
            logger.error("Gemini API call failed: %s", e)
            raise ExtractionError(f"LLM API call failed: {e}") from e

        # Parse JSON
        data = safe_json_parse(raw_response)

        # Inject raw_text (LLM doesn't set this)
        data["raw_text"] = raw_text

        # Validate with Pydantic
        try:
            result = ResumeStructured.model_validate(data)
        except Exception as e:
            logger.error("Pydantic validation failed: %s\nData: %s", e, str(data)[:500])
            raise ExtractionError(
                f"Extracted data failed schema validation: {e}",
                raw_response=raw_response,
            ) from e

        # Cache and return
        self._cache[text_hash] = result
        logger.info(
            "Resume extracted: %d skills, %d experiences, %d months total",
            len(result.skills),
            len(result.experience),
            result.total_experience_months,
        )
        return result

    def extract_from_file(self, file_path: str) -> ResumeStructured:
        """Extract from a file (PDF/DOCX/TXT) — handles text extraction first."""
        raw_text = extract_text_from_file(file_path)
        return self.extract(raw_text)


class JDExtractor:
    """
    Extracts structured JD data from raw text using Google Gemini.

    Usage:
        extractor = JDExtractor(settings)
        result = extractor.extract(raw_text)
        # result is a validated JDStructured instance
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._cache: dict[str, JDStructured] = {}
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            settings.extraction_model,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=8192,
            )
        )

    def extract(self, raw_text: str) -> JDStructured:
        """
        Extract structured data from JD text.
        Idempotent — cached by SHA256 hash of input.
        """
        text_hash = compute_hash(raw_text)

        # Cache hit
        if text_hash in self._cache:
            logger.debug("JD extraction cache hit: %s", text_hash[:12])
            return self._cache[text_hash]

        # Build prompt
        prompt = JD_EXTRACTION_PROMPT.format(
            schema=JD_SCHEMA,
            jd_text=raw_text[:8000],
        )

        # Call Gemini
        try:
            logger.info("Extracting JD with %s", self._settings.extraction_model)
            response = self._model.generate_content(prompt)
            raw_response = response.text
        except Exception as e:
            logger.error("Gemini API call failed: %s", e)
            raise ExtractionError(f"LLM API call failed: {e}") from e

        # Parse JSON
        data = safe_json_parse(raw_response)

        # Inject raw_text
        data["raw_text"] = raw_text

        # Validate with Pydantic
        try:
            result = JDStructured.model_validate(data)
        except Exception as e:
            logger.error("Pydantic validation failed: %s\nData: %s", e, str(data)[:500])
            raise ExtractionError(
                f"Extracted data failed schema validation: {e}",
                raw_response=raw_response,
            ) from e

        # Cache and return
        self._cache[text_hash] = result
        logger.info(
            "JD extracted: '%s' [%s], %d requirements, domain='%s'",
            result.title,
            result.level,
            len(result.requirements),
            result.domain,
        )
        return result

    def extract_from_file(self, file_path: str) -> JDStructured:
        """Extract from a file (PDF/DOCX/TXT) — handles text extraction first."""
        raw_text = extract_text_from_file(file_path)
        return self.extract(raw_text)
