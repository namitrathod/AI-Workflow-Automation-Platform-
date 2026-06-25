from __future__ import annotations

import time
import uuid
from typing import Any

from app.schemas.step import ToolStep
from app.steps.context import StepContext
from app.steps.registry import register
from app.steps.template import resolve_template


def _resolve_args(args: dict[str, Any], ctx: StepContext) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            resolved[key] = resolve_template(value, ctx)
        else:
            resolved[key] = value
    return resolved


@register("tool")
class ToolStepHandler:
    async def run(self, ctx: StepContext) -> dict[str, Any]:
        spec = ctx.step_spec
        if not isinstance(spec, ToolStep):
            raise TypeError("ToolStepHandler requires ToolStep")

        args = _resolve_args(spec.args, ctx)
        t0 = time.perf_counter()

        if spec.tool == "create_ticket":
            result = _create_ticket(args)
        else:
            raise ValueError(f"Unknown tool '{spec.tool}'")

        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "step": spec.id,
            "type": "tool",
            "result": result,
            "meta": {"tool": spec.tool, "duration_ms": duration_ms},
        }


def _create_ticket(args: dict[str, Any]) -> dict[str, Any]:
    ticket_id = f"TICK-{uuid.uuid4().hex[:8].upper()}"
    return {
        "ticket_id": ticket_id,
        "url": f"https://example.invalid/t/{ticket_id}",
        "title": args.get("title") or "Untitled",
        "priority": args.get("priority") or "medium",
        "summary": args.get("summary") or "",
    }
