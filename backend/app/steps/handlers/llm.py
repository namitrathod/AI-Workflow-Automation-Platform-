from __future__ import annotations

from typing import Any

from app.config import settings
from app.llm.json_parse import parse_json_content
from app.llm.ollama_provider import get_llm_provider
from app.schemas.step import LlmStep
from app.steps.context import StepContext
from app.steps.registry import register
from app.steps.template import resolve_template


@register("llm")
class LlmStepHandler:
    async def run(self, ctx: StepContext) -> dict[str, Any]:
        spec = ctx.step_spec
        if not isinstance(spec, LlmStep):
            raise TypeError("LlmStepHandler requires LlmStep")

        model = spec.model or settings.llm_default_model
        prompt = resolve_template(spec.prompt, ctx)
        provider = get_llm_provider()
        llm_result = await provider.complete(prompt, model=model, json_mode=bool(spec.output_schema))

        if spec.output_schema:
            result = parse_json_content(llm_result.content)
            for key in spec.output_schema:
                result.setdefault(key, "")
        else:
            result = {"text": llm_result.content}

        return {
            "step": spec.id,
            "type": "llm",
            "result": result,
            "meta": {
                "model": llm_result.model,
                "duration_ms": llm_result.duration_ms,
                "tokens_in": llm_result.tokens_in,
                "tokens_out": llm_result.tokens_out,
            },
        }
