from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.schemas.step import StepSpec


@dataclass
class StepContext:
    tenant_id: uuid.UUID
    job_id: uuid.UUID
    trigger: str
    payload: dict[str, Any] | None
    step_index: int
    step_spec: StepSpec
    prior_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def step_id(self) -> str:
        return self.step_spec.id
