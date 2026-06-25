from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class LlmStep(BaseModel):
    type: Literal["llm"] = "llm"
    id: str = Field(..., min_length=1, max_length=128)
    prompt: str = Field(..., min_length=1)
    model: str | None = Field(default=None, max_length=128)
    output_schema: dict[str, str] | None = None


class BuiltinStep(BaseModel):
    type: Literal["builtin"] = "builtin"
    id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)


class ToolStep(BaseModel):
    type: Literal["tool"] = "tool"
    id: str = Field(..., min_length=1, max_length=128)
    tool: str = Field(..., min_length=1, max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)


StepSpec = Annotated[LlmStep | BuiltinStep | ToolStep, Field(discriminator="type")]
