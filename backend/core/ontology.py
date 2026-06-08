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
    # ── Python Ecosystem ───────────────────────────────────────
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
    ("sqlalchemy", "database"),
    ("pydantic", "python"),
    ("streamlit", "python"),
    ("gradio", "python"),
    ("pytest", "python"),
    ("pytest", "testing"),
    ("poetry", "python"),
    ("pip", "python"),
    ("uvicorn", "python"),
    ("gunicorn", "python"),
    ("beautifulsoup", "python"),
    ("scrapy", "python"),
    ("selenium", "python"),
    ("selenium", "testing"),
    ("opencv", "python"),
    ("opencv", "computer vision"),
    ("matplotlib", "python"),
    ("seaborn", "python"),
    ("plotly", "python"),
    ("scipy", "python"),
    ("sympy", "python"),
    ("airflow", "python"),

    # ── JavaScript / TypeScript Ecosystem ──────────────────────
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
    ("svelte", "javascript"),
    ("remix", "react"),
    ("gatsby", "react"),
    ("webpack", "javascript"),
    ("vite", "javascript"),
    ("jest", "javascript"),
    ("jest", "testing"),
    ("mocha", "javascript"),
    ("mocha", "testing"),
    ("cypress", "javascript"),
    ("cypress", "testing"),
    ("playwright", "testing"),
    ("storybook", "frontend"),
    ("tailwindcss", "css"),
    ("bootstrap", "css"),
    ("sass", "css"),

    # ── Cloud & Infrastructure ─────────────────────────────────
    ("aws", "cloud computing"),
    ("gcp", "cloud computing"),
    ("azure", "cloud computing"),
    ("aws lambda", "serverless"),
    ("aws lambda", "aws"),
    ("aws s3", "aws"),
    ("aws ec2", "aws"),
    ("aws ecs", "aws"),
    ("aws ecs", "docker"),
    ("aws eks", "aws"),
    ("aws eks", "kubernetes"),
    ("aws sagemaker", "machine learning"),
    ("aws sagemaker", "aws"),
    ("aws sagemaker", "python"),
    ("aws bedrock", "aws"),
    ("aws bedrock", "llm"),
    ("azure devops", "azure"),
    ("azure devops", "devops"),
    ("azure functions", "azure"),
    ("azure functions", "serverless"),
    ("azure openai", "azure"),
    ("azure openai", "llm"),
    ("gcp cloud run", "gcp"),
    ("gcp cloud run", "serverless"),
    ("gcp vertex ai", "gcp"),
    ("gcp vertex ai", "machine learning"),
    ("firebase", "gcp"),
    ("firebase", "nosql"),
    ("supabase", "postgresql"),

    # ── DevOps & CI/CD ─────────────────────────────────────────
    ("kubernetes", "docker"),
    ("helm", "kubernetes"),
    ("docker compose", "docker"),
    ("podman", "docker"),
    ("terraform", "infrastructure as code"),
    ("ansible", "infrastructure as code"),
    ("ci/cd", "devops"),
    ("jenkins", "ci/cd"),
    ("github actions", "ci/cd"),
    ("gitlab ci", "ci/cd"),
    ("circleci", "ci/cd"),
    ("argocd", "ci/cd"),
    ("argocd", "kubernetes"),
    ("prometheus", "monitoring"),
    ("grafana", "monitoring"),
    ("datadog", "monitoring"),
    ("new relic", "monitoring"),
    ("nginx", "web server"),
    ("apache", "web server"),

    # ── GenAI / LLM Stack ──────────────────────────────────────
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
    ("large language models", "llm"),
    ("langchain", "python"),
    ("langchain", "llm"),
    ("langgraph", "langchain"),
    ("langgraph", "llm"),
    ("llamaindex", "python"),
    ("llamaindex", "llm"),
    ("rag", "llm"),
    ("retrieval augmented generation", "rag"),
    ("vector database", "database"),
    ("chromadb", "vector database"),
    ("pinecone", "vector database"),
    ("weaviate", "vector database"),
    ("qdrant", "vector database"),
    ("faiss", "vector database"),
    ("milvus", "vector database"),
    ("huggingface", "transformers"),
    ("hugging face", "transformers"),
    ("openai api", "llm"),
    ("gemini", "llm"),
    ("claude", "llm"),
    ("fine-tuning", "machine learning"),
    ("prompt engineering", "llm"),
    ("embeddings", "nlp"),
    ("sentence transformers", "transformers"),
    ("sentence transformers", "python"),
    ("lora", "fine-tuning"),
    ("qlora", "fine-tuning"),
    ("vllm", "llm"),
    ("ollama", "llm"),

    # ── Data Science / ML (expanded) ───────────────────────────
    ("xgboost", "machine learning"),
    ("lightgbm", "machine learning"),
    ("catboost", "machine learning"),
    ("random forest", "machine learning"),
    ("svm", "machine learning"),
    ("regression", "machine learning"),
    ("classification", "machine learning"),
    ("clustering", "machine learning"),
    ("gan", "deep learning"),
    ("diffusion models", "deep learning"),
    ("stable diffusion", "diffusion models"),
    ("reinforcement learning", "machine learning"),
    ("yolo", "computer vision"),
    ("object detection", "computer vision"),
    ("image segmentation", "computer vision"),
    ("mlflow", "machine learning"),
    ("wandb", "machine learning"),
    ("dvc", "machine learning"),
    ("feature engineering", "machine learning"),
    ("data preprocessing", "data science"),
    ("eda", "data science"),
    ("a/b testing", "data science"),

    # ── Databases ──────────────────────────────────────────────
    ("postgresql", "sql"),
    ("mysql", "sql"),
    ("sqlite", "sql"),
    ("mongodb", "nosql"),
    ("redis", "nosql"),
    ("elasticsearch", "nosql"),
    ("dynamodb", "nosql"),
    ("dynamodb", "aws"),
    ("cassandra", "nosql"),
    ("neo4j", "graph database"),
    ("neo4j", "database"),
    ("prisma", "database"),
    ("typeorm", "database"),
    ("drizzle", "database"),
    ("dbt", "sql"),

    # ── Data Engineering ───────────────────────────────────────
    ("apache spark", "big data"),
    ("pyspark", "apache spark"),
    ("pyspark", "python"),
    ("apache kafka", "distributed systems"),
    ("apache flink", "distributed systems"),
    ("hadoop", "big data"),
    ("hive", "big data"),
    ("snowflake", "data warehouse"),
    ("bigquery", "data warehouse"),
    ("bigquery", "gcp"),
    ("redshift", "data warehouse"),
    ("redshift", "aws"),
    ("databricks", "big data"),
    ("databricks", "apache spark"),

    # ── Java / JVM ─────────────────────────────────────────────
    ("spring boot", "java"),
    ("spring", "java"),
    ("maven", "java"),
    ("gradle", "java"),
    ("hibernate", "java"),
    ("junit", "java"),
    ("junit", "testing"),
    ("kotlin", "java"),
    ("scala", "jvm"),

    # ── Go / Rust / C++ ────────────────────────────────────────
    ("gin", "go"),
    ("echo", "go"),
    ("fiber", "go"),
    ("actix", "rust"),
    ("tokio", "rust"),
    ("rocket", "rust"),
    ("cmake", "c++"),
    ("qt", "c++"),

    # ── Mobile ─────────────────────────────────────────────────
    ("react native", "react"),
    ("react native", "javascript"),
    ("flutter", "dart"),
    ("swiftui", "swift"),
    ("jetpack compose", "kotlin"),

    # ── Security & Compliance ──────────────────────────────────
    ("oauth", "security"),
    ("jwt", "security"),
    ("ssl/tls", "security"),
    ("owasp", "security"),
    ("penetration testing", "security"),

    # ── Testing ────────────────────────────────────────────────
    ("postman", "api testing"),
    ("api testing", "testing"),
    ("unit testing", "testing"),
    ("integration testing", "testing"),
    ("load testing", "testing"),

    # ── Version Control & Project Management ───────────────────
    ("git", "version control"),
    ("github", "git"),
    ("gitlab", "git"),
    ("bitbucket", "git"),
    ("agile", "project management"),
    ("scrum", "agile"),
    ("kanban", "agile"),
    ("jira", "project management"),
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
