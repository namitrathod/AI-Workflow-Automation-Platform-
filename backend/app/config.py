from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg_async://postgres:postgres@localhost:5432/workflow_db"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Phase 3 — async queue (optional: leave unset to use synchronous POST /jobs/{id}/run only)
    redis_url: str | None = None
    queue_name: str = "workflow:jobs"
    dlq_name: str = "workflow:dlq"
    job_lock_ttl_seconds: int = 300
    worker_brpop_timeout: int = 5
    default_max_attempts: int = 3
    retry_backoff_cap_seconds: int = 60
    retry_on_workflow_failure: bool = False


settings = Settings()
