import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.step import StepSpec


class WorkflowDefinition(BaseModel):
    """Workflow body. String steps map to builtins; rich steps use llm/tool specs."""

    trigger: str = Field(..., min_length=1, max_length=128)
    steps: list[StepSpec] = Field(..., min_length=1)

    @field_validator("steps", mode="before")
    @classmethod
    def normalize_steps(cls, v: Any) -> Any:
        if not isinstance(v, list):
            raise ValueError("steps must be a list")
        out: list[Any] = []
        for item in v:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    raise ValueError("step names must be non-empty")
                out.append({"type": "builtin", "id": name, "name": name})
            else:
                out.append(item)
        return out


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    definition: WorkflowDefinition


class WorkflowRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    definition: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowListItem(BaseModel):
    id: uuid.UUID
    name: str
    trigger: str
    step_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    """Create job row; with Redis configured the API also enqueues for workers."""

    payload: dict | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=20)


class JobRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    payload: dict | None
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExecutionRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    step_index: int
    step_name: str
    status: str
    output: dict | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobDetailRead(JobRead):
    executions: list[ExecutionRead] = Field(default_factory=list)


class JobRunResult(JobDetailRead):
    """Returned after `POST .../run` — same shape as job detail."""

    pass
