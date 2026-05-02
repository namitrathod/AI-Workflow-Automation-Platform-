"""Redis list queue + DLQ helpers (Phase 3)."""

from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis

from app.config import settings

log = logging.getLogger(__name__)


async def push_job(redis: Redis, job_id: uuid.UUID) -> None:
    await redis.rpush(settings.queue_name, str(job_id))
    log.info("queue.enqueue job_id=%s queue=%s", job_id, settings.queue_name)


async def push_dlq(redis: Redis, job_id: uuid.UUID, reason: str) -> None:
    payload = json.dumps({"job_id": str(job_id), "reason": reason})
    await redis.rpush(settings.dlq_name, payload)
    log.warning("queue.dlq job_id=%s reason=%s", job_id, reason[:500])


async def brpop_job_id(redis: Redis) -> str | None:
    out = await redis.brpop(settings.queue_name, timeout=settings.worker_brpop_timeout)
    if out is None:
        return None
    _key, raw = out
    return raw if isinstance(raw, str) else raw.decode()


def lock_key(job_id: uuid.UUID) -> str:
    return f"workflow:lock:{job_id}"


async def acquire_lock(redis: Redis, job_id: uuid.UUID, token: str) -> bool:
    ok = await redis.set(lock_key(job_id), token, nx=True, ex=settings.job_lock_ttl_seconds)
    return bool(ok)


async def release_lock(redis: Redis, job_id: uuid.UUID, token: str) -> None:
    key = lock_key(job_id)
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
      return redis.call("del", KEYS[1])
    else
      return 0
    end
    """
    await redis.eval(lua, 1, key, token)
