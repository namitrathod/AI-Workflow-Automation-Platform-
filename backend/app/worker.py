"""Async worker: BRPOP from Redis, run workflow jobs with retries + DLQ.

Run from repo root / `backend`:

    python -m app.worker

Requires `REDIS_URL` and PostgreSQL (`DATABASE_URL`).
"""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as redis

from app.config import settings
from app.database import async_session_maker
from app.queue.redis_bus import brpop_job_id
from app.services.worker_processor import process_job_from_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    if not settings.redis_url:
        raise SystemExit("REDIS_URL must be set to run the worker.")

    client = redis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    log.info("worker.start queue=%s dlq=%s", settings.queue_name, settings.dlq_name)

    while True:
        raw = await brpop_job_id(client)
        if raw is None:
            continue
        async with async_session_maker() as session:
            try:
                await process_job_from_queue(session, client, raw)
            except Exception:  # noqa: BLE001
                log.exception("worker.tick_failed raw=%r", raw)


if __name__ == "__main__":
    asyncio.run(main())
