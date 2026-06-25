from __future__ import annotations

from typing import Any

from app.schemas.step import BuiltinStep, LlmStep, StepSpec, ToolStep
from app.steps.context import StepContext
from app.steps.handlers.llm import LlmStepHandler
from app.steps.handlers.tool import ToolStepHandler
from app.steps.registry import register

_BUILTIN_LLM: dict[str, LlmStep] = {
    "summarize_email": LlmStep(
        id="summarize_email",
        prompt=(
            "Summarize the following email for support routing.\n\n"
            "Subject: {{payload.subject}}\n"
            "Body: {{payload.body}}\n\n"
            "Reply with JSON only: {\"summary\": \"<one paragraph summary>\"}"
        ),
        output_schema={"summary": "string"},
    ),
    "classify_intent": LlmStep(
        id="classify_intent",
        prompt=(
            "Classify the customer intent and priority from this summary:\n\n"
            "{{steps.summarize_email.result.summary}}\n\n"
            "Reply with JSON only: "
            "{\"intent\": \"<short label>\", \"priority\": \"low|medium|high\"}"
        ),
        output_schema={"intent": "string", "priority": "string"},
    ),
}

_BUILTIN_TOOLS: dict[str, ToolStep] = {
    "create_ticket": ToolStep(
        id="create_ticket",
        tool="create_ticket",
        args={
            "title": "{{steps.classify_intent.result.intent}}",
            "priority": "{{steps.classify_intent.result.priority}}",
            "summary": "{{steps.summarize_email.result.summary}}",
        },
    ),
}


@register("builtin")
class BuiltinStepHandler:
    async def run(self, ctx: StepContext) -> dict[str, Any]:
        spec = ctx.step_spec
        if not isinstance(spec, BuiltinStep):
            raise TypeError("BuiltinStepHandler requires BuiltinStep")

        name = spec.name
        if name in _BUILTIN_LLM:
            llm_spec = _BUILTIN_LLM[name].model_copy(update={"id": spec.id})
            return await LlmStepHandler().run(_with_spec(ctx, llm_spec))
        if name in _BUILTIN_TOOLS:
            tool_spec = _BUILTIN_TOOLS[name].model_copy(update={"id": spec.id})
            return await ToolStepHandler().run(_with_spec(ctx, tool_spec))

        raise ValueError(f"Unknown builtin step '{name}'")


def _with_spec(ctx: StepContext, step_spec: StepSpec) -> StepContext:
    return StepContext(
        tenant_id=ctx.tenant_id,
        job_id=ctx.job_id,
        trigger=ctx.trigger,
        payload=ctx.payload,
        step_index=ctx.step_index,
        step_spec=step_spec,
        prior_outputs=ctx.prior_outputs,
    )
