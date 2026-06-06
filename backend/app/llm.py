"""Azure OpenAI wrapper (ADR-0006).

This deployment is an Azure AI Foundry project endpoint serving gpt-5.4-nano over
the OpenAI-compatible **v1** API (`{endpoint}/openai/v1/`, no api-version). Native
tool-calling does not reliably fire on nano, so we use **strict-JSON mode** as the
primary path (verified live). One entry point, `complete_json()`, returns a parsed
JSON object or None on any failure — the LLM must never break the loop.
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
    from openai import OpenAI  # imported lazily so tests/imports don't require it
    base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1/"
    return OpenAI(base_url=base_url, api_key=settings.AZURE_OPENAI_API_KEY)


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
    """Return a parsed JSON object from the model, or None on failure.

    Uses strict-JSON mode (the prompt must mention JSON). `tool` is accepted for
    compatibility but unused — native tool-calling is unreliable on this deployment;
    a `tool_calls` field is still parsed defensively if a model ever returns one.
    """
    client = client or _default_client()
    if client is None:
        return None
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT, messages=messages,
            response_format={"type": "json_object"},
        )
    except Exception:  # noqa: BLE001
        log.exception("LLM completion failed")
        return None
    try:
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None)
        if calls:
            return _loads(calls[0].function.arguments)
        return _loads(getattr(msg, "content", None))
    except Exception:  # noqa: BLE001
        return None
