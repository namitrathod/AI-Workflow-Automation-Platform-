import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.deps import get_current_user, get_redis
from app.models.job import Job
from app.models.user import User
from app.models.workflow import Workflow
from app.queue.redis_bus import push_job
from app.schemas.workflow import JobCreate, JobRead, WorkflowCreate, WorkflowListItem, WorkflowRead

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    wf = Workflow(
        tenant_id=current.tenant_id,
        owner_id=current.id,
        name=body.name,
        definition=body.definition.model_dump(),
    )
    session.add(wf)
    await session.commit()
    await session.refresh(wf)
    return wf


@router.get("", response_model=list[WorkflowListItem])
async def list_workflows(
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
) -> list[WorkflowListItem]:
    result = await session.execute(
        select(Workflow).where(Workflow.tenant_id == current.tenant_id).order_by(Workflow.created_at.desc())
    )
    rows = result.scalars().all()
    items: list[WorkflowListItem] = []
    for w in rows:
        d = w.definition or {}
        trigger = str(d.get("trigger", ""))
        steps = d.get("steps") or []
        step_count = len(steps) if isinstance(steps, list) else 0
        items.append(
            WorkflowListItem(
                id=w.id,
                name=w.name,
                trigger=trigger,
                step_count=step_count,
                created_at=w.created_at,
            )
        )
    return items


@router.get("/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(
    workflow_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    result = await session.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == current.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return wf


@router.post("/{workflow_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def enqueue_job(
    workflow_id: uuid.UUID,
    body: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current: Annotated[User, Depends(get_current_user)],
    redis=Depends(get_redis),
) -> Job:
    result = await session.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == current.tenant_id)
    )
    wf = result.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    max_attempts = body.max_attempts or settings.default_max_attempts
    use_queue = settings.redis_url and redis is not None
    job = Job(
        tenant_id=current.tenant_id,
        workflow_id=wf.id,
        status="queued" if use_queue else "pending",
        payload=body.payload,
        max_attempts=max_attempts,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    if use_queue:
        try:
            await push_job(redis, job.id)
        except Exception as exc:  # noqa: BLE001
            log.exception("queue.enqueue_failed job_id=%s", job.id)
            job.status = "pending"
            job.last_error = f"enqueue_failed: {exc}"[:4000]
            session.add(job)
            await session.commit()
            await session.refresh(job)
    return job
