from __future__ import annotations

import json
import re
from typing import Any

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise ValueError("Model returned empty content")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        block = _JSON_BLOCK.search(text)
        if block is None:
            raise ValueError(f"Model did not return valid JSON: {text[:300]}")
        parsed = json.loads(block.group(1).strip())

    if not isinstance(parsed, dict):
        raise ValueError("Model JSON must be an object")
    return parsed
