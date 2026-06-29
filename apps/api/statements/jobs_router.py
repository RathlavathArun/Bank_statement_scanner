"""Job progress endpoints."""
from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from core.celery_app import celery_app
from core.job_progress import get_job_progress
from db.database import get_db
from db.models import User
from statements.router import verify_statement_access

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    progress = get_job_progress(job_id)
    if progress and progress.get("statement_id"):
        await verify_statement_access(db, progress["statement_id"], current_user)

    result = AsyncResult(job_id, app=celery_app)
    if not progress:
        progress = {
            "job_id": job_id,
            "status": result.status,
            "stage": result.status.lower(),
            "progress": 100 if result.ready() else 0,
        }

    if result.failed():
        progress["status"] = "FAILED"
    elif result.successful() and progress.get("status") not in {"COMPLETED", "READY"}:
        progress["status"] = "COMPLETED"
        progress["progress"] = 100

    if result.status == "PENDING" and not get_job_progress(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    return {"success": True, "data": progress}
