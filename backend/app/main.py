import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, jobs, workflows
from app.config import settings
from app.database import Base, engine

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.redis = None
    if settings.redis_url:
        try:
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            await r.ping()
            app.state.redis = r
            log.info("redis.connected url=%s", settings.redis_url.split("@")[-1])
        except Exception as exc:  # noqa: BLE001
            log.warning("redis.unavailable — jobs stay pending unless REDIS_URL is fixed: %s", exc)
    yield
    r = getattr(app.state, "redis", None)
    if r is not None:
        await r.aclose()
    await engine.dispose()


app = FastAPI(
    title="AI Workflow Automation Platform",
    description="Multi-tenant workflow API (foundation for agent-style execution).",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
