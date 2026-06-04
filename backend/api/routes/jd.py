"""
Job Description API routes.

Endpoints:
- POST   /api/jd/upload   → Upload single JD (PDF/DOCX/TXT or raw text)
- GET    /api/jd/{id}      → Get JD structured data
- GET    /api/jd/          → List all JDs
- DELETE /api/jd/{id}      → Delete JD + vectors
"""

import logging
import os
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from core.vector_store import VectorStore
from db.postgres import JDRecord, get_db
from models.jd import JDListItem, JDUploadResponse
from workers.pipeline import Pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=JDUploadResponse)
async def upload_jd(
    file: UploadFile | None = File(None),
    raw_text: str | None = Body(None),
    settings: Settings = Depends(get_settings),
):
    """
    Upload a single job description.

    Accepts either:
    - A file (PDF/DOCX/TXT)
    - Raw text in the request body
    """
    jd_id = str(uuid.uuid4())
    os.makedirs(settings.upload_dir, exist_ok=True)

    if file and file.filename:
        # File upload
        allowed_types = {".pdf", ".docx", ".txt"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_types)}",
            )

        file_path = os.path.join(settings.upload_dir, f"jd_{jd_id}{ext}")
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info("Saved JD file: %s (%d bytes)", file_path, len(content))

    elif raw_text:
        # Raw text upload — save as .txt
        file_path = os.path.join(settings.upload_dir, f"jd_{jd_id}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        logger.info("Saved JD text: %s (%d chars)", file_path, len(raw_text))

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file or raw_text",
        )

    # Submit for async processing
    pipeline = Pipeline()
    result = pipeline.submit_jd(file_path, jd_id)

    return JDUploadResponse(
        jd_id=jd_id,
        status="processing",
        message=f"JD uploaded and queued for processing. Task ID: {result['task_id']}",
    )


@router.get("/{jd_id}")
async def get_jd(
    jd_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get structured data for a specific job description."""
    result = await db.execute(select(JDRecord).where(JDRecord.id == jd_id))
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' not found")

    return {
        "jd_id": record.id,
        "title": record.title,
        "level": record.level,
        "domain": record.domain,
        "structured": record.get_structured(),
        "requirements_count": record.requirements_count,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/")
async def list_jds(
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded job descriptions."""
    result = await db.execute(
        select(JDRecord).order_by(JDRecord.created_at.desc())
    )
    records = result.scalars().all()

    return [
        JDListItem(
            jd_id=r.id,
            title=r.title,
            level=r.level,
            domain=r.domain or "",
            requirements_count=r.requirements_count or 0,
            uploaded_at=r.created_at.isoformat() if r.created_at else None,
        ).model_dump()
        for r in records
    ]


@router.delete("/{jd_id}")
async def delete_jd(
    jd_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Delete a JD and its vectors."""
    result = await db.execute(select(JDRecord).where(JDRecord.id == jd_id))
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' not found")

    await db.delete(record)

    try:
        vs = VectorStore(settings)
        vs.delete_jd(jd_id)
    except Exception as e:
        logger.warning("Failed to delete vectors for JD '%s': %s", jd_id, e)

    return {"status": "deleted", "jd_id": jd_id}
