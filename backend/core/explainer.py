"""
Layer 5: Explainability Engine.

Generates human-readable match reports from MatchResult data.

Two modes:
1. Template-based: Always available, no API dependency
2. LLM-enhanced: Uses Gemini to generate a polished recommendation paragraph
"""

import logging
from typing import Optional

import google.generativeai as genai

from config import Settings
from models.match import MatchResult

logger = logging.getLogger(__name__)


class Explainer:
    """
    Generates human-readable explanations for match results.

    Usage:
        explainer = Explainer(settings)
        recommendation = explainer.generate_recommendation(match_result)
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = None

    def _get_model(self):
        """Lazy-init Gemini model for LLM-enhanced explanations."""
        if self._model is None and self._settings.google_api_key:
            genai.configure(api_key=self._settings.google_api_key)
            self._model = genai.GenerativeModel(self._settings.extraction_model)
        return self._model

    def generate_template_recommendation(self, result: MatchResult) -> str:
        """
        Generate a recommendation using templates (no API needed).
        Always reliable, deterministic output.
        """
        parts: list[str] = []

        # Overall assessment
        grade_descriptions = {
            "A": "an excellent match",
            "B": "a strong match",
            "C": "a moderate match",
            "D": "a weak match",
            "F": "not a good match",
        }
        assessment = grade_descriptions.get(result.grade, "a match")
        parts.append(
            f"This candidate is {assessment} with an overall score of "
            f"{result.overall_score:.0f}/100 (Grade: {result.grade})."
        )

        # Skills highlights
        skills = result.skills_score
        if skills.matched:
            parts.append(
                f"Skills alignment is strong with {len(skills.matched)} direct "
                f"match(es): {', '.join(skills.matched[:5])}."
            )
        if skills.partial:
            parts.append(
                f"Additionally, {len(skills.partial)} skill(s) are partially "
                f"matched: {', '.join(skills.partial[:3])}."
            )
        if skills.missing:
            parts.append(
                f"However, {len(skills.missing)} required skill(s) are missing: "
                f"{', '.join(skills.missing[:5])}."
            )

        # Experience highlights
        exp = result.experience_score
        if exp.notes:
            parts.append(f"Experience: {exp.notes}.")

        # Red flags
        if result.red_flags:
            parts.append(
                "Red flags to consider: " + "; ".join(result.red_flags[:3]) + "."
            )

        # Final recommendation
        if result.grade in ("A", "B"):
            parts.append("Recommendation: Proceed to interview.")
        elif result.grade == "C":
            parts.append(
                "Recommendation: Consider for a screening call to assess "
                "gaps in skills or experience."
            )
        else:
            parts.append(
                "Recommendation: Not a strong fit for this role based on "
                "current requirements."
            )

        return " ".join(parts)

    def generate_llm_recommendation(self, result: MatchResult) -> Optional[str]:
        """
        Generate a polished recommendation using Google Gemini.
        Falls back to template if API is unavailable.
        """
        model = self._get_model()
        if model is None:
            return None

        prompt = f"""You are an expert HR analyst. Write a concise, professional 
recommendation paragraph (3-5 sentences) for a hiring manager based on this 
match analysis.

Overall Score: {result.overall_score:.0f}/100 (Grade: {result.grade})

Skills Analysis:
- Matched: {', '.join(result.skills_score.matched[:8]) or 'None'}
- Partially Matched: {', '.join(result.skills_score.partial[:5]) or 'None'}
- Missing Required: {', '.join(result.skills_score.missing[:5]) or 'None'}

Experience: {result.experience_score.notes}
Education: {result.education_score.notes}
Projects: {result.projects_score.notes}

Red Flags: {', '.join(result.red_flags[:5]) or 'None'}

Write a balanced, actionable recommendation. Be specific about strengths and gaps.
Do NOT use bullet points. Write flowing prose only."""

        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.warning("LLM recommendation failed, using template: %s", e)
            return None

    def generate_recommendation(self, result: MatchResult) -> str:
        """
        Generate the best available recommendation.
        Tries LLM first if enabled, falls back to template.
        """
        # Try LLM-enhanced if enabled in settings
        if self._settings.explainer_use_llm:
            llm_rec = self.generate_llm_recommendation(result)
            if llm_rec:
                return llm_rec

        # Fallback to template
        return self.generate_template_recommendation(result)

    def enrich_match_result(self, result: MatchResult) -> MatchResult:
        """
        Add recommendation text to a match result.
        Returns a new MatchResult with the recommendation filled in.
        """
        recommendation = self.generate_recommendation(result)
        return result.model_copy(update={"recommendation": recommendation})
