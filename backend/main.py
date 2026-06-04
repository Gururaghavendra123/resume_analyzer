"""
Resume & JD Analyzer — FastAPI Application Entry Point.

This is the main application file that:
- Creates the FastAPI app with CORS and lifespan
- Includes all API routers
- Sets up logging
- Manages startup/shutdown lifecycle (DB, vector store init)
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import LoggingMiddleware
from api.routes import resume, jd, match
from config import get_settings
from db.postgres import init_db, close_db

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("Starting Resume & JD Analyzer [%s]", settings.app_env)

    # Create uploads directory
    os.makedirs(settings.upload_dir, exist_ok=True)

    # Initialize database tables
    await init_db()
    logger.info("Database initialized")

    # Initialize vector store collections
    from core.vector_store import VectorStore
    vs = VectorStore(settings)
    vs.ensure_collections()
    logger.info("Vector store collections ready")

    # API Key check
    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY is not set! LLM extraction will fail.")
    else:
        logger.info("Google API Key is set")

    # Redis check
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        logger.info("Redis connection OK")
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)

    yield  # App is running

    # Shutdown
    await close_db()
    logger.info("Shutdown complete")


# ── App ────────────────────────────────────────────────────────
app = FastAPI(
    title="Resume & JD Analyzer",
    description=(
        "Semantically match resumes to job descriptions with explainable scores. "
        "ML-powered matching engine using transformer embeddings and "
        "section-weighted scoring."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware ─────────────────────────────────────────────────
app.add_middleware(LoggingMiddleware)

# ── Routers ────────────────────────────────────────────────────
app.include_router(resume.router, prefix="/api/resume", tags=["Resumes"])
app.include_router(jd.router, prefix="/api/jd", tags=["Job Descriptions"])
app.include_router(match.router, prefix="/api/match", tags=["Matching"])


# ── Health Check ───────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "resume-jd-analyzer"}
