"""Model-agnostic chat-model layer over LangChain (ADR-0010).

Supersedes the hand-rolled OpenAI-SDK wrapper (ADR-0006): the model is now a
LangChain `BaseChatModel` selected by config (`LLM_PROVIDER`, `LLM_MODEL`), so
swapping Azure OpenAI for Ollama (or another provider) needs no code change. The
default is the Azure AI Foundry **v1** endpoint (`{endpoint}/openai/v1/`, no
api-version) via `ChatOpenAI(base_url=…)` — not `AzureChatOpenAI`, which forces
an api-version.

Native tool-calling does not reliably fire on nano (verified live), so **JSON
mode** remains the primary path. One entry point, `complete_json()`, returns a
parsed JSON object or None on any failure — the LLM must never break the loop.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from .config import settings

log = logging.getLogger("llm")


def available() -> bool:
    provider = settings.LLM_PROVIDER
    if provider == "azure-openai":
        return bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT
                    and (settings.LLM_MODEL or settings.AZURE_OPENAI_DEPLOYMENT))
    if provider == "ollama":
        return bool(settings.LLM_MODEL)
    return False


def _fast_model_name() -> str:
    """The cheap/default model — drafts the activity log, and is the fallback for
    in-loop reasoning when LLM_REASONING_MODEL is unset (ADR-0011)."""
    return settings.LLM_MODEL or settings.AZURE_OPENAI_DEPLOYMENT


# Built chat models are memoised by (provider, model, endpoint) so the agent loop
# reuses one HTTP connection pool instead of constructing a fresh client — and a
# fresh TLS handshake — on every diagnose/plan/draft call.
_model_cache: Dict[str, Any] = {}


def _build_model(model_name: str) -> Any:
    """Build (and memoise) a LangChain chat model for a specific model name (ADR-0011).

    Provider is taken from config; packages are imported lazily inside each
    branch so an optional provider's package being absent never breaks the
    default (azure) path. All providers run in JSON mode.
    """
    provider = settings.LLM_PROVIDER
    cache_key = f"{provider}|{model_name}|{settings.AZURE_OPENAI_ENDPOINT}|{settings.OLLAMA_BASE_URL}"
    cached = _model_cache.get(cache_key)
    if cached is not None:
        return cached

    if provider == "azure-openai":
        from langchain_openai import ChatOpenAI  # lazy: keeps imports cheap
        base_url = settings.AZURE_OPENAI_ENDPOINT.rstrip("/") + "/openai/v1/"
        # Deliberately NO temperature: gpt-5.x / o-series reasoning models reject any
        # non-default temperature with a 400, and langchain-openai<0.3.28 forwards it
        # verbatim. The endpoint default is correct for our strict-JSON output (ADR-0011).
        model = ChatOpenAI(
            base_url=base_url,
            api_key=settings.AZURE_OPENAI_API_KEY,
            model=model_name,
        )
        built = model.bind(response_format={"type": "json_object"})
    elif provider == "ollama":
        from langchain_ollama import ChatOllama  # lazy: optional package
        # Local models are not reasoning SKUs, so a deterministic temperature is safe.
        built = ChatOllama(
            model=model_name,
            base_url=settings.OLLAMA_BASE_URL,
            format="json",
            temperature=0,
        )
    else:
        log.warning("unknown LLM_PROVIDER %r — no model built", provider)
        return None

    _model_cache[cache_key] = built
    return built


def _default_model() -> Any:
    """The fast model, or None when unavailable."""
    return _build_model(_fast_model_name()) if available() else None


def _reasoning_model() -> Any:
    """The stronger model for in-loop reasoning (ADR-0011); falls back to the fast model.

    Used for every diagnose/plan decision; the fast model is reserved for the
    non-reasoning activity-log draft.
    """
    if not available():
        return None
    return _build_model(settings.LLM_REASONING_MODEL or _fast_model_name())


def _loads(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Tolerant JSON parse — handles code fences and surrounding prose.

    `content` may be a non-string (LangChain types it `str | list`); anything
    that is not a usable string yields None rather than raising.
    """
    if not isinstance(text, str) or not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if len(lines) > 1:
            body = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
            t = "\n".join(body).strip()
        else:
            # Single-line fence (```{...}``` or ```json {...}```): strip the backticks
            # and an optional language tag rather than dropping the body to "".
            t = t.strip("`").strip()
            if t.lower().startswith("json"):
                t = t[4:].strip()
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


def complete_json(system: str, user: str, *, model: Any = None,
                  reasoning: bool = False) -> Optional[Dict[str, Any]]:
    """Return a parsed JSON object from the model, or None on failure.

    Uses JSON mode (the prompt must mention JSON). `model` is an injectable
    LangChain chat model — anything with `.invoke(messages) -> obj` whose
    `obj.content` is a string. When omitted, the model is built from config:
    the stronger reasoning model when `reasoning=True` (ADR-0011), else the
    fast model.

    Returning None degrades the agent to its read-only baseline, so the two
    *failure* paths (a configured provider that errors, or one that returns
    unparseable content) are logged at WARNING — distinct from the silent,
    expected "no provider configured" path, which returns None without a log.
    """
    try:
        if model is None:
            model = _reasoning_model() if reasoning else _default_model()
        if model is None:
            return None  # no provider configured — expected, not a failure
        msg = model.invoke([("system", system), ("human", user)])
        result = _loads(getattr(msg, "content", None))
        if result is None:
            log.warning("LLM returned no parseable JSON (provider=%s, reasoning=%s) — "
                        "degrading to baseline.", settings.LLM_PROVIDER, reasoning)
        return result
    except Exception:  # noqa: BLE001
        # Covers a missing optional provider package (ImportError from a lazy
        # import), transport errors, and rejected request params (e.g. sending a
        # temperature a reasoning model won't accept). The LLM must never break the
        # loop, but a *configured* provider failing every call is a real
        # misconfiguration — surface it instead of swallowing it silently.
        log.warning(
            "LLM call failed (provider=%s, reasoning=%s) — degrading to read-only "
            "baseline; verify credentials, model name, and unsupported request "
            "params (e.g. temperature on a reasoning model).",
            settings.LLM_PROVIDER, reasoning, exc_info=True,
        )
        return None
