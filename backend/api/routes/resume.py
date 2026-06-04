"""
Resume API routes.

Endpoints:
- POST   /api/resume/upload        → Upload single resume (PDF/DOCX/TXT)
- POST   /api/resume/bulk-upload   → Upload multiple resumes
- GET    /api/resume/{id}          → Get resume structured data
- GET    /api/resume/              → List all resumes
- DELETE /api/resume/{id}          → Delete resume + vectors
"""

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from core.vector_store import VectorStore
from db.postgres import ResumeRecord, get_db
from models.resume import ResumeListItem, ResumeStructured, ResumeUploadResponse
from workers.pipeline import Pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_pipeline() -> Pipeline:
    return Pipeline()


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    """
    Upload a single resume file for processing.

    Accepts: PDF, DOCX, TXT
    Processing happens async via Celery.
    """
    # Validate file type
    allowed_types = {".pdf", ".docx", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_types)}",
        )

    # Save file
    resume_id = str(uuid.uuid4())
    file_path = os.path.join(settings.upload_dir, f"{resume_id}{ext}")
    os.makedirs(settings.upload_dir, exist_ok=True)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info("Saved resume file: %s (%d bytes)", file_path, len(content))

    # Submit for async processing
    pipeline = _get_pipeline()
    result = pipeline.submit_resume(file_path, resume_id)

    return ResumeUploadResponse(
        resume_id=resume_id,
        status="processing",
        message=f"Resume uploaded and queued for processing. Task ID: {result['task_id']}",
    )


@router.post("/bulk-upload")
async def bulk_upload_resumes(
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
):
    """Upload multiple resume files for parallel processing."""
    allowed_types = {".pdf", ".docx", ".txt"}
    file_paths: list[str] = []

    os.makedirs(settings.upload_dir, exist_ok=True)

    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in allowed_types:
            logger.warning("Skipping unsupported file: %s", file.filename)
            continue

        file_id = str(uuid.uuid4())
        file_path = os.path.join(settings.upload_dir, f"{file_id}{ext}")

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        file_paths.append(file_path)

    if not file_paths:
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    pipeline = _get_pipeline()
    result = pipeline.bulk_upload_resumes(file_paths)

    return {
        "job_id": result["job_id"],
        "total_files": result["total"],
        "resume_ids": result["resume_ids"],
        "status": "processing",
        "message": f"{result['total']} resumes queued for processing",
    }


@router.get("/")
async def list_resumes(
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded resumes."""
    result = await db.execute(
        select(ResumeRecord).order_by(ResumeRecord.created_at.desc())
    )
    records = result.scalars().all()

    return [
        ResumeListItem(
            resume_id=r.id,
            candidate_name=r.candidate_name,
            total_experience_months=r.total_experience_months or 0,
            skills_count=r.skills_count or 0,
            domains=r.get_domains(),
            uploaded_at=r.created_at.isoformat() if r.created_at else None,
        ).model_dump()
        for r in records
    ]


@router.get("/{resume_id}")
async def get_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get structured data for a specific resume."""
    result = await db.execute(
        select(ResumeRecord).where(ResumeRecord.id == resume_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")

    structured = record.get_structured()
    return {
        "resume_id": record.id,
        "candidate_name": record.candidate_name,
        "structured": structured,
        "skills_count": record.skills_count,
        "total_experience_months": record.total_experience_months,
        "domains": record.get_domains(),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Delete a resume and its vectors."""
    # Delete from DB
    result = await db.execute(
        select(ResumeRecord).where(ResumeRecord.id == resume_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail=f"Resume '{resume_id}' not found")

    await db.delete(record)

    # Delete from vector store
    try:
        vs = VectorStore(settings)
        vs.delete_resume(resume_id)
    except Exception as e:
        logger.warning("Failed to delete vectors for '%s': %s", resume_id, e)

    return {"status": "deleted", "resume_id": resume_id}
