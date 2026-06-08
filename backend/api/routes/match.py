"""
Match API routes.

Endpoints:
- POST /api/match/run                  → Trigger match job (JD vs all resumes)
- GET  /api/match/results/{job_id}     → Poll async match job status/results
- GET  /api/match/{resume_id}/{jd_id}  → Get specific match result
- GET  /api/match/export/{job_id}      → Export results as JSON
- GET  /api/match/export/{job_id}/pdf  → Export results as PDF report
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.postgres import MatchRecord, get_db
from models.match import MatchRequest
from workers.pipeline import Pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run")
async def run_match(request: MatchRequest):
    """
    Trigger a match job: match one JD against all resumes.

    The matching runs asynchronously via Celery.
    Use GET /api/match/results/{job_id} to poll for results.
    """
    pipeline = Pipeline()
    result = pipeline.submit_match(
        jd_id=request.jd_id,
        top_k=request.top_k,
        domain=request.filters.domain if request.filters else None,
        min_experience_years=(
            request.filters.min_experience_years if request.filters else None
        ),
    )

    return {
        "job_id": result["job_id"],
        "jd_id": request.jd_id,
        "status": "pending",
        "message": "Match job submitted. Poll /api/match/results/{job_id} for results.",
    }


@router.get("/results/{job_id}")
async def get_match_results(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get results for a match job.

    First checks Celery task status, then loads results from DB.
    """
    # Check Celery task status
    pipeline = Pipeline()
    task_status = pipeline.get_task_status(job_id)

    if task_status["status"] == "pending":
        return {"job_id": job_id, "status": "pending", "results": []}

    if task_status["status"] == "processing":
        return {"job_id": job_id, "status": "processing", "results": []}

    if task_status["status"] == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": task_status.get("error", "Unknown error"),
            "results": [],
        }

    # Load results from DB
    result = await db.execute(
        select(MatchRecord)
        .where(MatchRecord.job_id == job_id)
        .order_by(MatchRecord.overall_score.desc())
    )
    records = result.scalars().all()

    results = [record.get_result() for record in records]

    return {
        "job_id": job_id,
        "status": "completed",
        "results_count": len(results),
        "results": results,
    }


@router.get("/detail/{resume_id}/{jd_id}")
async def get_specific_match(
    resume_id: str,
    jd_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific match result between a resume and JD."""
    result = await db.execute(
        select(MatchRecord)
        .where(MatchRecord.resume_id == resume_id, MatchRecord.jd_id == jd_id)
        .order_by(MatchRecord.created_at.desc())
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No match found for resume '{resume_id}' and JD '{jd_id}'",
        )

    return record.get_result()


@router.get("/export/{job_id}")
async def export_match_results(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Export match results as a downloadable JSON."""
    result = await db.execute(
        select(MatchRecord)
        .where(MatchRecord.job_id == job_id)
        .order_by(MatchRecord.overall_score.desc())
    )
    records = result.scalars().all()

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No results found for job '{job_id}'",
        )

    results = [record.get_result() for record in records]

    return JSONResponse(
        content={
            "job_id": job_id,
            "export_format": "json",
            "results_count": len(results),
            "results": results,
        },
        headers={
            "Content-Disposition": f"attachment; filename=match_results_{job_id}.json"
        },
    )


@router.get("/export/{job_id}/pdf")
async def export_match_results_pdf(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Export match results as a downloadable professional PDF report."""
    from fastapi.responses import Response
    from db.postgres import JDRecord
    from core.pdf_export import generate_match_report_pdf

    # Load match records
    result = await db.execute(
        select(MatchRecord)
        .where(MatchRecord.job_id == job_id)
        .order_by(MatchRecord.overall_score.desc())
    )
    records = result.scalars().all()

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No results found for job '{job_id}'",
        )

    results = [record.get_result() for record in records]

    # Try to get JD title for the cover page
    jd_title = "Job Description"
    jd_id = results[0].get("jd_id") if results else None
    if jd_id:
        jd_result = await db.execute(select(JDRecord).where(JDRecord.id == jd_id))
        jd_record = jd_result.scalar_one_or_none()
        if jd_record and jd_record.title:
            jd_title = jd_record.title

    # Generate PDF
    try:
        pdf_bytes = generate_match_report_pdf(results, jd_title=jd_title, job_id=job_id)
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=match_report_{job_id[:8]}.pdf",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
