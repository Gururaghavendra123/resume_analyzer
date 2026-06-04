"""
Pipeline orchestration for bulk processing.

Coordinates multiple Celery tasks for batch uploads and matching.
Provides job status tracking and progress reporting.
"""

import logging
import uuid

# pyrefly: ignore [missing-import]
from celery import group

from workers.tasks import process_resume, process_jd, run_match_job

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates async processing pipelines.

    Usage:
        pipeline = Pipeline()
        job_id = pipeline.bulk_upload_resumes(file_paths)
        status = pipeline.get_job_status(job_id)
    """

    def submit_resume(self, file_path: str, resume_id: str | None = None) -> dict:
        """
        Submit a single resume for processing.

        Returns:
            dict with resume_id and task_id for tracking
        """
        rid = resume_id or str(uuid.uuid4())
        task = process_resume.delay(file_path, rid)
        logger.info("Submitted resume '%s' → task '%s'", rid, task.id)
        return {"resume_id": rid, "task_id": task.id, "status": "pending"}

    def submit_jd(self, file_path: str, jd_id: str | None = None) -> dict:
        """Submit a single JD for processing."""
        jid = jd_id or str(uuid.uuid4())
        task = process_jd.delay(file_path, jid)
        logger.info("Submitted JD '%s' → task '%s'", jid, task.id)
        return {"jd_id": jid, "task_id": task.id, "status": "pending"}

    def bulk_upload_resumes(
        self, file_paths: list[str]
    ) -> dict:
        """
        Submit multiple resumes for parallel processing.

        Uses Celery group to fan out tasks.
        """
        job_id = str(uuid.uuid4())
        tasks = []
        resume_ids = []

        for fp in file_paths:
            rid = str(uuid.uuid4())
            resume_ids.append(rid)
            tasks.append(process_resume.s(fp, rid))

        # Launch all tasks in parallel
        job = group(tasks).apply_async()
        logger.info(
            "Bulk upload job '%s': %d resumes submitted", job_id, len(tasks)
        )

        return {
            "job_id": job_id,
            "group_id": job.id,
            "resume_ids": resume_ids,
            "total": len(tasks),
            "status": "processing",
        }

    def submit_match(
        self,
        jd_id: str,
        top_k: int = 10,
        domain: str | None = None,
        min_experience_years: float | None = None,
    ) -> dict:
        """Submit a match job for async processing."""
        task = run_match_job.delay(jd_id, top_k, domain, min_experience_years)
        logger.info("Submitted match job for JD '%s' → task '%s'", jd_id, task.id)
        return {"job_id": task.id, "jd_id": jd_id, "status": "pending"}

    def get_task_status(self, task_id: str) -> dict:
        """Check the status of a Celery task."""
        # pyrefly: ignore [missing-import]
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        status_map = {
            "PENDING": "pending",
            "STARTED": "processing",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "RETRY": "retrying",
        }

        response = {
            "task_id": task_id,
            "status": status_map.get(result.status, result.status),
        }

        if result.successful():
            response["result"] = result.result
        elif result.failed():
            response["error"] = str(result.result)

        return response
