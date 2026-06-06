#!/usr/bin/env python3
"""Smoke check 3/3 — LLM seam (LangChain, model-agnostic; ADR-0010).

Exercises the real backend seam (`app.llm`) rather than a raw provider call, so this
works for whatever `LLM_PROVIDER` is configured (azure-openai default, or ollama).
LangChain builds the chat model behind `complete_json()`; JSON mode stays the primary
path (native tool-calling is unreliable on nano). Returns a parsed dict or None.

Run:  python scripts/smoke/check_llm.py
"""
import os
import sys
from pathlib import Path

from _env import load_env, ok, fail

# Make the backend package importable without installing it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "backend"))


def main() -> int:
    load_env()

    # Guard the import: the LangChain-backed seam pulls heavy deps that may not be
    # installed yet while the code rewrite is in flight. Degrade clearly, don't crash.
    try:
        from app import llm
        from app.config import settings
    except Exception as e:  # noqa: BLE001
        fail(f"could not import app.llm ({type(e).__name__}: {e})")
        print("  install the backend deps (langchain + provider package) and retry.")
        return 2

    provider = getattr(settings, "LLM_PROVIDER", "azure-openai")
    model = getattr(settings, "LLM_MODEL", "") or getattr(settings, "AZURE_OPENAI_DEPLOYMENT", "") or "(provider default)"
    print(f"LLM seam: provider={provider}  model={model}")

    if not llm.available():
        fail("llm.available() is False — provider creds/config are missing.")
        if provider == "azure-openai":
            print("  set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY (+ deployment) in .env.")
        elif provider == "ollama":
            print("  set LLM_MODEL and ensure Ollama is running at OLLAMA_BASE_URL.")
        else:
            print("  configure the selected LLM_PROVIDER in .env.")
        return 2

    system = "You are a smoke test. Reply with strict JSON only."
    user = 'Return this JSON exactly: {"action":"diagnose","command":"uname -a"}'
    try:
        result = llm.complete_json(system, user)
    except Exception as e:  # noqa: BLE001
        fail(f"complete_json raised ({type(e).__name__}: {e})")
        return 1

    if isinstance(result, dict):
        ok(f"complete_json -> {result!r}  (JSON mode works — the agent path)")
        return 0
    fail(f"complete_json returned {result!r} (expected a parsed dict)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
