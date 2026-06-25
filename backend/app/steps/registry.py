from __future__ import annotations

from typing import Any, Protocol

from app.steps.context import StepContext


class StepHandler(Protocol):
    async def run(self, ctx: StepContext) -> dict[str, Any]: ...


_handlers: dict[str, StepHandler] = {}


def register(step_type: str):
    def decorator(cls: type[StepHandler]) -> type[StepHandler]:
        _handlers[step_type] = cls()
        return cls

    return decorator


async def run_step(ctx: StepContext) -> dict[str, Any]:
    handler = _handlers.get(ctx.step_spec.type)
    if handler is None:
        raise ValueError(f"No handler registered for step type '{ctx.step_spec.type}'")
    return await handler.run(ctx)


def ensure_handlers_loaded() -> None:
    import app.steps.handlers  # noqa: F401 — register handlers via side effect
