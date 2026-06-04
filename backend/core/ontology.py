"""
Layer 4b: Skill Ontology Graph.

Directed graph where edges mean: "knowing X implies knowing/being capable of Y".
Used by the scoring engine for transitive skill matching.

Sources:
- ESCO v1.2 (European Skills/Competences Qualification) — seed data
- Domain-specific manual implications (e.g. PyTorch → Python)

Uses networkx DiGraph for path-based inference.
"""

import logging
from typing import Optional

import networkx as nx

from models.resume import Skill

logger = logging.getLogger(__name__)


# ── Seed Implications ──────────────────────────────────────────
# (skill_known, skill_implied) — knowing the left implies the right
SEED_IMPLICATIONS: list[tuple[str, str]] = [
    # Python ecosystem
    ("pytorch", "python"),
    ("tensorflow", "python"),
    ("keras", "python"),
    ("keras", "tensorflow"),
    ("fastapi", "python"),
    ("django", "python"),
    ("flask", "python"),
    ("pandas", "python"),
    ("numpy", "python"),
    ("scikit-learn", "python"),
    ("scikit-learn", "machine learning"),
    ("celery", "python"),
    ("sqlalchemy", "python"),
    ("pydantic", "python"),

    # JavaScript ecosystem
    ("react", "javascript"),
    ("nextjs", "react"),
    ("nextjs", "javascript"),
    ("next.js", "react"),
    ("next.js", "javascript"),
    ("angular", "javascript"),
    ("angular", "typescript"),
    ("vue", "javascript"),
    ("vue.js", "javascript"),
    ("nuxt", "vue"),
    ("nuxt", "javascript"),
    ("express", "nodejs"),
    ("express", "javascript"),
    ("nodejs", "javascript"),
    ("node.js", "javascript"),
    ("typescript", "javascript"),

    # Cloud & DevOps
    ("kubernetes", "docker"),
    ("helm", "kubernetes"),
    ("terraform", "infrastructure as code"),
    ("ansible", "infrastructure as code"),
    ("aws", "cloud computing"),
    ("gcp", "cloud computing"),
    ("azure", "cloud computing"),
    ("aws lambda", "serverless"),
    ("aws lambda", "aws"),
    ("aws sagemaker", "machine learning"),
    ("aws sagemaker", "aws"),
    ("aws sagemaker", "python"),

    # Data & ML
    ("deep learning", "machine learning"),
    ("neural networks", "deep learning"),
    ("computer vision", "deep learning"),
    ("nlp", "machine learning"),
    ("natural language processing", "machine learning"),
    ("transformers", "deep learning"),
    ("transformers", "nlp"),
    ("bert", "transformers"),
    ("gpt", "transformers"),
    ("llm", "transformers"),
    ("langchain", "python"),
    ("langchain", "llm"),

    # Databases
    ("postgresql", "sql"),
    ("mysql", "sql"),
    ("sqlite", "sql"),
    ("mongodb", "nosql"),
    ("redis", "nosql"),
    ("elasticsearch", "nosql"),

    # Mobile
    ("react native", "react"),
    ("react native", "javascript"),
    ("flutter", "dart"),
    ("swiftui", "swift"),
    ("jetpack compose", "kotlin"),
    ("kotlin", "java"),

    # Data Engineering
    ("apache spark", "big data"),
    ("apache kafka", "distributed systems"),
    ("airflow", "python"),
    ("dbt", "sql"),

    # General
    ("git", "version control"),
    ("github", "git"),
    ("gitlab", "git"),
    ("ci/cd", "devops"),
    ("jenkins", "ci/cd"),
    ("github actions", "ci/cd"),
    ("agile", "project management"),
    ("scrum", "agile"),
]


class OntologyGraph:
    """
    Directed graph of skill implications.

    Edge (A → B) means "knowing A implies capability in B".
    Uses transitive path search: if A → B → C, then knowing A implies C.

    Usage:
        ontology = OntologyGraph()
        ontology.load_seed_data()
        implied = ontology.is_implied_by_resume("python", resume_skills)
        # Returns the skill name that implies "python", or None
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def add_implication(self, skill_known: str, skill_implied: str) -> None:
        """
        Add a directed edge: knowing skill_known implies skill_implied.

        All skill names are lowercased for case-insensitive matching.
        """
        self.graph.add_edge(skill_known.lower(), skill_implied.lower())

    def load_seed_data(self) -> None:
        """Load the built-in seed implications."""
        for known, implied in SEED_IMPLICATIONS:
            self.add_implication(known, implied)
        logger.info(
            "Ontology loaded: %d nodes, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    def is_implied_by_resume(
        self, required_skill: str, resume_skills: list[Skill]
    ) -> Optional[str]:
        """
        Check if any resume skill implies the required skill via
        transitive graph traversal.

        Args:
            required_skill: The skill the JD requires.
            resume_skills: List of skills from the resume.

        Returns:
            The name of the resume skill that implies the required skill,
            or None if no implication found.
        """
        req = required_skill.lower()

        # If the required skill isn't even in our graph, can't infer
        if req not in self.graph:
            return None

        for skill in resume_skills:
            known = skill.name.lower()
            if known not in self.graph:
                continue
            try:
                if nx.has_path(self.graph, known, req):
                    return skill.name
            except nx.NetworkXError:
                continue

        return None

    def get_implied_skills(self, skill_name: str) -> list[str]:
        """
        Get all skills that are implied by knowing a given skill.
        (All reachable nodes from the skill in the graph.)
        """
        skill = skill_name.lower()
        if skill not in self.graph:
            return []
        return list(nx.descendants(self.graph, skill))

    def get_implying_skills(self, skill_name: str) -> list[str]:
        """
        Get all skills that imply the given skill.
        (All ancestors of the skill in the graph.)
        """
        skill = skill_name.lower()
        if skill not in self.graph:
            return []
        return list(nx.ancestors(self.graph, skill))
