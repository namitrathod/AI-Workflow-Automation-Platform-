"""Synchronous (in-request) workflow runner — Phase 2 execution tracking.

Phase 3 replaces the transport with a queue + workers; this module stays the core step runner.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.execution import Execution
from app.models.job import Job
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowDefinition


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _run_step_logic(
    step_name: str,
    trigger: str,
    job_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Placeholder step implementations — swap for LLM/tools in Phase 4."""
    base: dict[str, Any] = {
        "step": step_name,
        "trigger": trigger,
        "payload_keys": sorted((job_payload or {}).keys()),
    }
    stubs: dict[str, dict[str, Any]] = {
        "summarize_email": {"summary": "(stub) Email summarized for routing."},
        "classify_intent": {"intent": "support_request", "priority": "medium"},
        "create_ticket": {"ticket_id": "stub-TICK-1001", "url": "https://example.invalid/t/stub-TICK-1001"},
    }
    if step_name in stubs:
        return {**base, **stubs[step_name]}
    return {**base, "result": "completed", "note": "generic stub; map step names in workflow_engine for richer output"}


async def run_job(session: AsyncSession, job: Job, workflow: Workflow) -> Job:
    """Execute all steps in order; persists `Execution` rows and updates `Job` status."""
    await session.execute(delete(Execution).where(Execution.job_id == job.id))

    job.status = "running"
    job.started_at = job.started_at or _utcnow()
    job.completed_at = None
    job.last_error = None
    session.add(job)
    await session.flush()

    try:
        definition = WorkflowDefinition.model_validate(workflow.definition or {})
    except Exception as exc:  # noqa: BLE001 — validation errors become a failed execution row
        job.status = "failed"
        job.completed_at = _utcnow()
        job.last_error = f"Invalid workflow definition: {exc}"[:4000]
        session.add(job)
        ex = Execution(
            tenant_id=job.tenant_id,
            job_id=job.id,
            step_index=0,
            step_name="__workflow_validate__",
            status="failed",
            error=f"Invalid workflow definition: {exc}",
            started_at=_utcnow(),
            completed_at=_utcnow(),
        )
        session.add(ex)
        await session.commit()
        return await _reload_job(session, job.id)

    steps = definition.steps
    trigger = definition.trigger

    for idx, step_name in enumerate(steps):
        ex = Execution(
            tenant_id=job.tenant_id,
            job_id=job.id,
            step_index=idx,
            step_name=step_name,
            status="running",
            started_at=_utcnow(),
        )
        session.add(ex)
        await session.flush()
        try:
            output = await _run_step_logic(step_name, trigger, job.payload)
            ex.status = "completed"
            ex.output = output
            ex.error = None
        except Exception as run_exc:  # noqa: BLE001
            ex.status = "failed"
            ex.error = str(run_exc)
            ex.output = None
            ex.completed_at = _utcnow()
            job.status = "failed"
            job.completed_at = _utcnow()
            job.last_error = str(run_exc)[:4000]
            session.add(job)
            await session.commit()
            return await _reload_job(session, job.id)
        ex.completed_at = _utcnow()
        session.add(ex)

    job.status = "completed"
    job.completed_at = _utcnow()
    job.last_error = None
    session.add(job)
    await session.commit()
    return await _reload_job(session, job.id)


async def _reload_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    result = await session.execute(
        select(Job).where(Job.id == job_id).options(selectinload(Job.executions), selectinload(Job.workflow))
    )
    return result.scalar_one()


async def load_job_for_tenant(
    session: AsyncSession, job_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[Job | None, Workflow | None]:
    result = await session.execute(
        select(Job)
        .where(Job.id == job_id, Job.tenant_id == tenant_id)
        .options(selectinload(Job.workflow), selectinload(Job.executions))
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None, None
    return job, job.workflow
