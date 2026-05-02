import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_session
from app.deps import get_current_user, get_redis
from app.models.job import Job
from app.models.user import User
from app.queue.redis_bus import push_job
from app.schemas.workflow import ExecutionRead, JobDetailRead, JobRead, JobRunResult
from app.services.workflow_engine import load_job_for_tenant, run_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _sorted_executions(job: Job) -> list[ExecutionRead]:
    rows = sorted(job.executions, key=lambda e: e.step_index)
    return [ExecutionRead.model_validate(x) for x in rows]


def _job_detail(job: Job) -> JobDetailRead:
    return JobDetailRead(
        id=job.id,
        tenant_id=job.tenant_id,
        workflow_id=job.workflow_id,
        status=job.status,
        payload=job.payload,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        executions=_sorted_executions(job),
    )


@router.get("", response_model=list[JobRead])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
    workflow_id: uuid.UUID | None = Query(default=None, description="Filter by workflow"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Job]:
    q = select(Job).where(Job.tenant_id == current.tenant_id).order_by(Job.created_at.desc()).limit(limit)
    if workflow_id is not None:
        q = q.where(Job.workflow_id == workflow_id)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.get("/{job_id}", response_model=JobDetailRead)
async def get_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
) -> JobDetailRead:
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id, Job.tenant_id == current.tenant_id)
        .options(selectinload(Job.executions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_detail(job)


@router.post("/{job_id}/run", response_model=JobRunResult)
async def run_job_endpoint(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
    redis=Depends(get_redis),
) -> JobRunResult:
    job, workflow = await load_job_for_tenant(session, job_id, current.tenant_id)
    if job is None or workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    use_queue = settings.redis_url and redis is not None
    allowed = ("queued", "pending", "failed") if use_queue else ("pending", "failed")
    if job.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job cannot be run in status '{job.status}' (allowed: {', '.join(allowed)}).",
        )
    if use_queue:
        job.status = "queued"
        job.attempt_count = 0
        job.last_error = None
        session.add(job)
        await session.commit()
        try:
            await push_job(redis, job.id)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.last_error = f"enqueue_failed: {exc}"[:4000]
            session.add(job)
            await session.commit()
        await session.refresh(job)
        result = await session.execute(
            select(Job)
            .where(Job.id == job.id, Job.tenant_id == current.tenant_id)
            .options(selectinload(Job.executions))
        )
        fresh = result.scalar_one()
        return JobRunResult(**_job_detail(fresh).model_dump())

    updated = await run_job(session, job, workflow)
    return JobRunResult(**_job_detail(updated).model_dump())
