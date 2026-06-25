from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.llm.errors import LlmConnectionError, LlmResponseError
from app.llm.provider import LlmResult


def _ollama_root(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    path = parsed.path.removesuffix("/v1").rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class OllamaProvider:
    async def complete(self, prompt: str, *, model: str, json_mode: bool = False) -> LlmResult:
        root = _ollama_root(settings.ollama_base_url)
        url = f"{root}/api/chat"
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if json_mode:
            body["format"] = "json"

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(url, json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LlmConnectionError(
                f"Ollama request failed ({url}). Is Ollama running and is '{model}' pulled? Error: {exc}"
            ) from exc

        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise LlmResponseError(f"Ollama returned empty content for model '{model}'")

        duration_ms = int((time.perf_counter() - t0) * 1000)
        prompt_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")
        return LlmResult(
            content=content,
            model=model,
            duration_ms=duration_ms,
            tokens_in=int(prompt_tokens) if prompt_tokens is not None else None,
            tokens_out=int(output_tokens) if output_tokens is not None else None,
        )


_provider: OllamaProvider | None = None


def get_llm_provider() -> OllamaProvider:
    global _provider
    if _provider is None:
        _provider = OllamaProvider()
    return _provider
