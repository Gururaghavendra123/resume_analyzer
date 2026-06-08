"""
Admin API routes.

Endpoints:
- DELETE /api/admin/flush  → Wipe ALL data (PostgreSQL + Qdrant + Redis + uploads)
"""

import glob
import logging
import os

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from core.vector_store import VectorStore
from db.postgres import JDRecord, MatchRecord, ResumeRecord, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.delete("/flush")
async def flush_all_data(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Nuclear option: wipe ALL data from every store.

    Clears:
    - PostgreSQL: resumes, job_descriptions, match_results tables
    - Qdrant: deletes and recreates both collections
    - Redis: flushes the Celery task queue
    - Filesystem: deletes all files in ./uploads/

    Use this to get a clean slate before re-uploading.
    """
    summary = {}

    # 1. Count existing records for the summary
    resumes_count = (await db.execute(select(func.count()).select_from(ResumeRecord))).scalar() or 0
    jds_count = (await db.execute(select(func.count()).select_from(JDRecord))).scalar() or 0
    matches_count = (await db.execute(select(func.count()).select_from(MatchRecord))).scalar() or 0

    # 2. Delete from PostgreSQL (order matters: match_results first due to references)
    await db.execute(delete(MatchRecord))
    await db.execute(delete(JDRecord))
    await db.execute(delete(ResumeRecord))
    await db.flush()

    summary["resumes_deleted"] = resumes_count
    summary["jds_deleted"] = jds_count
    summary["matches_deleted"] = matches_count
    logger.info(
        "Flushed PostgreSQL: %d resumes, %d JDs, %d matches",
        resumes_count, jds_count, matches_count,
    )

    # 3. Purge Qdrant collections (delete + recreate)
    try:
        vs = VectorStore(settings)
        client = vs._get_client()

        for collection_name in [
            settings.qdrant_collection_resumes,
            settings.qdrant_collection_jds,
        ]:
            try:
                client.delete_collection(collection_name)
                logger.info("Deleted Qdrant collection '%s'", collection_name)
            except Exception:
                pass  # Collection might not exist

        # Recreate empty collections
        vs.ensure_collections()
        summary["vectors"] = "purged and recreated"
        logger.info("Qdrant collections recreated")
    except Exception as e:
        summary["vectors"] = f"error: {e}"
        logger.warning("Failed to purge Qdrant: %s", e)

    # 4. Flush Redis (Celery queue)
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.flushdb()
        summary["redis"] = "flushed"
        logger.info("Redis flushed")
    except Exception as e:
        summary["redis"] = f"error: {e}"
        logger.warning("Failed to flush Redis: %s", e)

    # 5. Delete uploaded files
    upload_dir = settings.upload_dir
    deleted_files = 0
    if os.path.isdir(upload_dir):
        for filepath in glob.glob(os.path.join(upload_dir, "*")):
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                    deleted_files += 1
                except OSError:
                    pass
    summary["uploads_deleted"] = deleted_files
    logger.info("Deleted %d upload files", deleted_files)

    return {
        "status": "flushed",
        "summary": summary,
    }
