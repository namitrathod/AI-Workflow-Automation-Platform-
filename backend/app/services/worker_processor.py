"""Worker-side job processing: attempts, retries, DLQ, timing logs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.job import Job
from app.queue.redis_bus import acquire_lock, push_dlq, push_job, release_lock
from app.services.workflow_engine import run_job

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt_after_increment: int) -> float:
    base = 2 ** max(0, attempt_after_increment - 1)
    return float(min(base, settings.retry_backoff_cap_seconds))


async def process_job_from_queue(session: AsyncSession, redis: Any, job_id_str: str) -> None:
    try:
        job_uuid = uuid.UUID(job_id_str.strip())
    except ValueError:
        log.error("worker.invalid_job_id raw=%r", job_id_str)
        return

    lock_token = str(uuid.uuid4())
    if not await acquire_lock(redis, job_uuid, lock_token):
        log.info("worker.lock_busy job_id=%s requeue", job_uuid)
        await push_job(redis, job_uuid)
        await asyncio.sleep(0.2)
        return

    t0 = time.perf_counter()
    try:
        result = await session.execute(
            select(Job).where(Job.id == job_uuid).options(selectinload(Job.workflow))
        )
        job = result.scalar_one_or_none()
        if job is None:
            log.error("worker.job_missing job_id=%s", job_uuid)
            return

        if job.status in ("completed", "dlq"):
            log.info("worker.skip_terminal job_id=%s status=%s", job_uuid, job.status)
            return

        if job.status == "running":
            log.warning("worker.skip_running job_id=%s", job_uuid)
            return

        if job.status not in ("queued", "pending", "failed"):
            log.info("worker.skip_status job_id=%s status=%s", job_uuid, job.status)
            return

        workflow = job.workflow
        if workflow is None:
            job.status = "failed"
            job.last_error = "Workflow missing for job"
            job.completed_at = _utcnow()
            session.add(job)
            await session.commit()
            log.error("worker.workflow_missing job_id=%s", job_uuid)
            return

        job.attempt_count += 1
        if job.attempt_count > job.max_attempts:
            job.status = "dlq"
            job.last_error = f"Exceeded max_attempts={job.max_attempts} (pre-run guard)"
            session.add(job)
            await session.commit()
            await push_dlq(redis, job_uuid, job.last_error)
            log.warning(
                "worker.dlq_pre_run job_id=%s attempts=%s max=%s",
                job_uuid,
                job.attempt_count,
                job.max_attempts,
            )
            return

        session.add(job)
        await session.commit()
        await session.refresh(job)

        log.info(
            "worker.run_start job_id=%s attempt=%s/%s",
            job_uuid,
            job.attempt_count,
            job.max_attempts,
        )

        try:
            await run_job(session, job, workflow)
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            log.exception(
                "worker.run_exception job_id=%s attempt=%s elapsed_ms=%s",
                job_uuid,
                job.attempt_count,
                elapsed_ms,
            )
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            await _handle_infra_failure(session, redis, job_uuid, str(exc))
            return

        row_res = await session.execute(select(Job).where(Job.id == job_uuid))
        row = row_res.scalar_one()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "worker.run_done job_id=%s status=%s attempt=%s elapsed_ms=%s",
            job_uuid,
            row.status,
            row.attempt_count,
            elapsed_ms,
        )

        if row.status == "failed" and settings.retry_on_workflow_failure:
            if row.attempt_count < row.max_attempts:
                row.status = "queued"
                row.last_error = (row.last_error or "")[:4000] or "workflow_failed_retry"
                session.add(row)
                await session.commit()
                delay = _backoff_seconds(row.attempt_count)
                log.warning(
                    "worker.retry_workflow_failure job_id=%s attempt=%s backoff_s=%s",
                    job_uuid,
                    row.attempt_count,
                    delay,
                )
                await asyncio.sleep(delay)
                await push_job(redis, job_uuid)
            else:
                row.status = "dlq"
                row.last_error = (row.last_error or "workflow_failed_max_retries")[:4000]
                session.add(row)
                await session.commit()
                await push_dlq(redis, job_uuid, row.last_error or "workflow_failed")
                log.warning("worker.dlq_workflow job_id=%s", job_uuid)
    finally:
        await release_lock(redis, job_uuid, lock_token)


async def _handle_infra_failure(session: AsyncSession, redis: Any, job_uuid: uuid.UUID, err: str) -> None:
    result = await session.execute(select(Job).where(Job.id == job_uuid))
    job = result.scalar_one_or_none()
    if job is None:
        return
    if job.status in ("completed", "dlq"):
        return
    if job.attempt_count < job.max_attempts:
        job.status = "queued"
        job.last_error = err[:4000]
        session.add(job)
        await session.commit()
        delay = _backoff_seconds(job.attempt_count)
        log.warning(
            "worker.retry_infra job_id=%s attempt=%s/%s backoff_s=%s err=%s",
            job_uuid,
            job.attempt_count,
            job.max_attempts,
            delay,
            err[:500],
        )
        await asyncio.sleep(delay)
        await push_job(redis, job_uuid)
        return

    job.status = "dlq"
    job.last_error = err[:4000]
    session.add(job)
    await session.commit()
    await push_dlq(redis, job_uuid, err[:2000])
    log.error("worker.dlq_infra job_id=%s attempts=%s err=%s", job_uuid, job.attempt_count, err[:500])
