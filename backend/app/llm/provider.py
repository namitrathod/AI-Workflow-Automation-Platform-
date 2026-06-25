from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LlmResult:
    content: str
    model: str
    duration_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None


class LlmProvider(Protocol):
    async def complete(self, prompt: str, *, model: str, json_mode: bool = False) -> LlmResult: ...
