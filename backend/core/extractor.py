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


# ── Batch Extraction Prompt ────────────────────────────────────

BATCH_RESUME_EXTRACTION_PROMPT = """You are a precise resume parser. Extract structured information from EACH of the {n} resumes below.

Return ONLY a valid JSON array with exactly {n} objects (one per resume, in the same order).
No preamble. No explanation. No markdown fences.

Each object must match this schema exactly:
{schema}

Rules:
- If a field cannot be determined, use null.
- For recency: "current" if used in last 12 months, "recent" if 1-3 years, "old" if 3+ years.
- Calculate total_experience_months from all non-overlapping experience entries.
- CRITICAL: Extract ATOMIC, single-concept skills. DO NOT extract comma-separated lists as one skill!
- The output array must have EXACTLY {n} elements.

Resumes (separated by ===RESUME_SEPARATOR===):

{resumes_block}"""


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
    cleaned = strip_markdown_fences(raw).lstrip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Fallback: parse the first valid JSON object and ignore trailing extra data
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(cleaned)
            return obj
        except json.JSONDecodeError:
            pass

        logger.error("JSON parse failed: %s\nRaw response:\n%s", e, raw[:500])
        raise ExtractionError(
            f"LLM returned invalid JSON: {e}",
            raw_response=raw,
        ) from e


# ── Content Hashing ────────────────────────────────────────────

def compute_hash(text: str) -> str:
    """SHA256 hash of input text for idempotent caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── API Key Rotation ───────────────────────────────────

import itertools
import time


class APIKeyRotator:
    """
    Round-robin API key rotation with automatic failover.

    If GOOGLE_API_KEYS is set (comma-separated), cycles through them.
    On a 429/quota error the next key is tried automatically.
    Falls back to the single GOOGLE_API_KEY if GOOGLE_API_KEYS is empty.
    """

    def __init__(self, settings: Settings):
        keys: list[str] = []
        if settings.google_api_keys:
            keys = [k.strip() for k in settings.google_api_keys.split(",") if k.strip()]
        if not keys and settings.google_api_key:
            keys = [settings.google_api_key]
        if not keys:
            raise ExtractionError("No Google API keys configured. Set GOOGLE_API_KEY or GOOGLE_API_KEYS.")

        self._keys = keys
        self._cycle = itertools.cycle(range(len(keys)))
        self._current_idx = next(self._cycle)
        logger.info("API key rotator initialized with %d key(s)", len(keys))

    @property
    def current_key(self) -> str:
        return self._keys[self._current_idx]

    def rotate(self) -> str:
        """Advance to the next key and return it."""
        self._current_idx = next(self._cycle)
        logger.info("Rotated to API key #%d / %d", self._current_idx + 1, len(self._keys))
        return self.current_key

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    def configure_current(self):
        """Configure genai with the current key."""
        genai.configure(api_key=self.current_key)

    def call_with_rotation(self, model, prompt, max_retries: int = 3):
        """
        Call generate_content with auto-rotation on 429 errors.
        Tries each key once before giving up.
        """
        attempts = 0
        keys_tried = 0
        last_error = None

        while keys_tried < self.total_keys and attempts < max_retries:
            self.configure_current()
            try:
                response = model.generate_content(prompt)
                return response
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
                    logger.warning(
                        "API key #%d hit rate limit: %s — rotating...",
                        self._current_idx + 1, str(e)[:120],
                    )
                    self.rotate()
                    keys_tried += 1
                    attempts += 1
                    time.sleep(1)  # small cooldown
                    last_error = e
                else:
                    raise  # non-rate-limit error, bubble up

        raise ExtractionError(
            f"All {self.total_keys} API key(s) exhausted after {attempts} attempts. Last error: {last_error}"
        )


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
        self._rotator = APIKeyRotator(settings)
        self._rotator.configure_current()
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

        # Call Gemini (with key rotation on 429)
        try:
            logger.info("Extracting resume with %s", self._settings.extraction_model)
            response = self._rotator.call_with_rotation(self._model, prompt)
            raw_response = response.text
        except ExtractionError:
            raise
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

    def batch_extract(self, raw_texts: list[str]) -> list[ResumeStructured]:
        """
        Extract structured data from multiple resumes in ONE Gemini API call.

        Packs up to 6 resumes into a single prompt, returning a list of
        ResumeStructured objects. Falls back to sequential individual extraction
        per resume if the batch call fails or returns wrong count.

        Saves 5x API calls on bulk uploads compared to sequential extraction.
        """
        if not raw_texts:
            return []

        # Check cache — skip already-cached ones
        results: list[Optional[ResumeStructured]] = [None] * len(raw_texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(raw_texts):
            text_hash = compute_hash(text)
            if text_hash in self._cache:
                logger.debug("Batch: resume %d cache hit", i)
                results[i] = self._cache[text_hash]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if not uncached_texts:
            return results  # type: ignore[return-value]

        n = len(uncached_texts)
        logger.info("Batch extracting %d resumes in one API call", n)

        # Build the combined prompt
        resumes_block = "\n\n===RESUME_SEPARATOR===\n\n".join(
            f"[RESUME {i+1}]\n{text[:6000]}" for i, text in enumerate(uncached_texts)
        )
        prompt = BATCH_RESUME_EXTRACTION_PROMPT.format(
            n=n,
            schema=RESUME_SCHEMA,
            resumes_block=resumes_block,
        )

        try:
            # Use a higher token limit for batch
            batch_model = genai.GenerativeModel(
                self._settings.extraction_model,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=16384,
                )
            )
            response = batch_model.generate_content(prompt)
            raw_response = response.text
        except Exception as e:
            logger.warning("Batch extraction API call failed: %s — falling back to sequential", e)
            # Fallback: extract each resume individually
            for i, (orig_idx, text) in enumerate(zip(uncached_indices, uncached_texts)):
                try:
                    results[orig_idx] = self.extract(text)
                except Exception as ex:
                    logger.error("Sequential fallback failed for resume %d: %s", orig_idx, ex)
                    raise
            return results  # type: ignore[return-value]

        # Parse the JSON array
        try:
            data_list = safe_json_parse(raw_response)
            if not isinstance(data_list, list):
                raise ValueError(f"Expected JSON array, got {type(data_list).__name__}")
            if len(data_list) != n:
                raise ValueError(f"Expected {n} results, got {len(data_list)}")
        except Exception as e:
            logger.warning("Batch JSON parse failed: %s — falling back to sequential", e)
            for orig_idx, text in zip(uncached_indices, uncached_texts):
                try:
                    results[orig_idx] = self.extract(text)
                except Exception as ex:
                    logger.error("Sequential fallback failed: %s", ex)
                    raise
            return results  # type: ignore[return-value]

        # Validate each parsed item
        for batch_i, (orig_idx, text) in enumerate(zip(uncached_indices, uncached_texts)):
            data = data_list[batch_i]
            data["raw_text"] = text
            try:
                structured = ResumeStructured.model_validate(data)
                self._cache[compute_hash(text)] = structured
                results[orig_idx] = structured
                logger.info(
                    "Batch resume %d: %d skills, %d months exp",
                    orig_idx + 1, len(structured.skills), structured.total_experience_months,
                )
            except Exception as e:
                logger.warning("Validation failed for batch item %d: %s — falling back", batch_i, e)
                results[orig_idx] = self.extract(text)  # individual fallback

        return results  # type: ignore[return-value]


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
        self._rotator = APIKeyRotator(settings)
        self._rotator.configure_current()
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

        # Call Gemini (with key rotation on 429)
        try:
            logger.info("Extracting JD with %s", self._settings.extraction_model)
            response = self._rotator.call_with_rotation(self._model, prompt)
            raw_response = response.text
        except ExtractionError:
            raise
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
