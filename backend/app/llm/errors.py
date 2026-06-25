class LlmError(Exception):
    """Base error for LLM provider failures."""


class LlmConnectionError(LlmError):
    """Ollama unreachable or network failure."""


class LlmResponseError(LlmError):
    """Empty or malformed model response."""
