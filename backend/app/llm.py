"""Azure OpenAI wrapper (ADR-0006).

One thin entry point: `complete_json()` returns a parsed JSON object from the
model, or None on any failure (the LLM must never break the loop). Dual-mode:
native function/tool calling is preferred; if the deployment rejects tools or
returns text, it falls back to strict-JSON mode. The rest of the codebase never
imports the OpenAI SDK directly.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .config import settings

log = logging.getLogger("llm")


def available() -> bool:
    return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT
                and settings.AZURE_OPENAI_DEPLOYMENT)


def _default_client():
    if not available():
        return None
    from openai import AzureOpenAI  # imported lazily so tests/imports don't require it
    return AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.AZURE_OPENAI_API_KEY,
        api_version=settings.AZURE_OPENAI_API_VERSION,
    )


def _loads(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Tolerant JSON parse — handles code fences and surrounding prose."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(t[i:j + 1])
            except Exception:  # noqa: BLE001
                return None
        return None


def complete_json(system: str, user: str, *, tool: Optional[Dict[str, Any]] = None,
                  client: Any = None) -> Optional[Dict[str, Any]]:
    """Return a parsed JSON object from the model, or None on failure."""
    client = client or _default_client()
    if client is None:
        return None
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    deployment = settings.AZURE_OPENAI_DEPLOYMENT

    # 1) Native tool-calling (preferred).
    if tool is not None:
        try:
            resp = client.chat.completions.create(
                model=deployment, messages=messages,
                tools=[{"type": "function", "function": tool}], tool_choice="auto",
            )
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None)
            if calls:
                return _loads(calls[0].function.arguments)
            parsed = _loads(getattr(msg, "content", None))
            if parsed is not None:
                return parsed
        except Exception:  # noqa: BLE001
            log.warning("native tool-calling failed; falling back to JSON mode")

    # 2) Strict-JSON fallback.
    try:
        resp = client.chat.completions.create(
            model=deployment, messages=messages,
            response_format={"type": "json_object"},
        )
        return _loads(resp.choices[0].message.content)
    except Exception:  # noqa: BLE001
        log.exception("LLM JSON completion failed")
        return None
