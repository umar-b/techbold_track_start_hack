"""Small Azure OpenAI wrapper.

The app asks the model for JSON actions instead of giving it direct tools. If
Azure is missing or fails, this module returns None so the safe fallback path can
keep the run moving.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .config import settings

log = logging.getLogger("llm")


def available() -> bool:
    """Return True only when all Azure settings needed for a call are present."""

    return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT
                and settings.AZURE_OPENAI_DEPLOYMENT)


def _default_client():
    """Create the OpenAI-compatible Azure client lazily."""

    if not available():
        return None
    from openai import OpenAI  # imported lazily so tests/imports don't require it
    base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1/"
    return OpenAI(base_url=base_url, api_key=settings.AZURE_OPENAI_API_KEY)


def _loads(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse JSON even if the model adds code fences or a little extra prose."""
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

    The run loop must never crash because of the LLM. This catches API failures,
    malformed responses, and optional tool-call output, then lets callers decide
    whether to use fallback logic.
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
