"""
Custom exception classes — one per architectural layer.

Every layer raises its own typed exception. Never raise bare Exception.
These are caught by the API middleware and Celery retry logic.
"""


class ExtractionError(Exception):
    """Raised when LLM extraction fails or produces invalid output."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    def __init__(self, message: str, section: str | None = None):
        super().__init__(message)
        self.section = section


class ScoringError(Exception):
    """Raised when scoring computation fails."""

    def __init__(self, message: str, resume_id: str | None = None, jd_id: str | None = None):
        super().__init__(message)
        self.resume_id = resume_id
        self.jd_id = jd_id


class VectorStoreError(Exception):
    """Raised when vector DB operations fail."""

    def __init__(self, message: str, collection: str | None = None):
        super().__init__(message)
        self.collection = collection


class DocumentParseError(Exception):
    """Raised when PDF/DOCX parsing fails."""

    def __init__(self, message: str, file_path: str | None = None):
        super().__init__(message)
        self.file_path = file_path
