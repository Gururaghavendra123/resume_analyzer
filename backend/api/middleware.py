"""
Request logging and error handling middleware.

Logs all incoming requests with timing information.
Catches unhandled exceptions and returns structured error responses.
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.exceptions import (
    DocumentParseError,
    EmbeddingError,
    ExtractionError,
    ScoringError,
    VectorStoreError,
)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Logs every request with method, path, status, and duration
    2. Catches typed exceptions and returns appropriate HTTP status codes
    3. Catches all other exceptions and returns 500
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            duration = (time.perf_counter() - start_time) * 1000

            logger.info(
                "%s %s → %d (%.1fms)",
                method,
                path,
                response.status_code,
                duration,
            )
            return response

        except DocumentParseError as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("%s %s → 400 DocumentParseError: %s (%.1fms)", method, path, e, duration)
            return JSONResponse(
                status_code=400,
                content={"error": "document_parse_error", "detail": str(e)},
            )

        except ExtractionError as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("%s %s → 422 ExtractionError: %s (%.1fms)", method, path, e, duration)
            return JSONResponse(
                status_code=422,
                content={"error": "extraction_error", "detail": str(e)},
            )

        except EmbeddingError as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("%s %s → 500 EmbeddingError: %s (%.1fms)", method, path, e, duration)
            return JSONResponse(
                status_code=500,
                content={"error": "embedding_error", "detail": str(e)},
            )

        except VectorStoreError as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("%s %s → 503 VectorStoreError: %s (%.1fms)", method, path, e, duration)
            return JSONResponse(
                status_code=503,
                content={"error": "vector_store_error", "detail": str(e)},
            )

        except ScoringError as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error("%s %s → 500 ScoringError: %s (%.1fms)", method, path, e, duration)
            return JSONResponse(
                status_code=500,
                content={"error": "scoring_error", "detail": str(e)},
            )

        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "%s %s → 500 Unhandled: %s (%.1fms)", method, path, e, duration
            )
            return JSONResponse(
                status_code=500,
                content={"error": "internal_error", "detail": "An unexpected error occurred"},
            )
