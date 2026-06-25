"""Synchronous (in-request) workflow runner — Phase 2 execution tracking.

Phase 3 replaces the transport with a queue + workers; this module stays the core step runner.
Phase 4 runs steps via the registry (LLM via Ollama/Gemma, tools, builtins).
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
from app.steps.context import StepContext
from app.steps.registry import ensure_handlers_loaded, run_step


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def run_job(session: AsyncSession, job: Job, workflow: Workflow) -> Job:
    """Execute all steps in order; persists `Execution` rows and updates `Job` status."""
    ensure_handlers_loaded()
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

    trigger = definition.trigger
    prior_outputs: dict[str, dict[str, Any]] = {}

    for idx, step_spec in enumerate(definition.steps):
        step_name = step_spec.id
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
        ctx = StepContext(
            tenant_id=job.tenant_id,
            job_id=job.id,
            trigger=trigger,
            payload=job.payload,
            step_index=idx,
            step_spec=step_spec,
            prior_outputs=prior_outputs,
        )
        try:
            output = await run_step(ctx)
            prior_outputs[step_name] = output
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
