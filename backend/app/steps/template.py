from __future__ import annotations

import re
from typing import Any

from app.steps.context import StepContext

_TEMPLATE_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


def resolve_template(template: str, ctx: StepContext) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group(1).strip()
        value = resolve_path(path, ctx)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            import json

            return json.dumps(value)
        return str(value)

    return _TEMPLATE_PATTERN.sub(replace, template)


def resolve_path(path: str, ctx: StepContext) -> Any:
    parts = path.split(".")
    if not parts:
        return ""

    root = parts[0]
    rest = parts[1:]

    if root == "trigger":
        return ctx.trigger if not rest else _walk(ctx.trigger, rest)

    if root == "payload":
        return _walk(ctx.payload or {}, rest)

    if root == "steps":
        if not rest:
            return ctx.prior_outputs
        step_id, *tail = rest
        step_output = ctx.prior_outputs.get(step_id, {})
        return _walk(step_output, tail)

    raise ValueError(f"Unknown template root '{root}' in path '{path}'")


def _walk(obj: Any, parts: list[str]) -> Any:
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return ""
    return current if current is not None else ""
