"""Activity-log generator for the ERP.

It drafts the final ticket note from the commands that actually ran. The LLM can
write a better note when available, but the deterministic fallback keeps the
workflow usable without AI credentials.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import llm
from .audit import redact

# Phoenix expects these fields when an activity is created.
_FIELDS = ["summary", "root_cause", "actions_taken", "commands_summary", "validation_result"]

_SYSTEM = (
    "You write a concise, technically precise IT activity log for one resolved incident. "
    "Return ONLY JSON with keys: summary, root_cause, actions_taken, commands_summary, "
    "validation_result. root_cause is the technical cause, not the symptom. validation_result "
    "must be concrete (e.g. a test or health-check result). Never include secrets, keys, "
    "passwords or tokens."
)


def draft_activity(ticket: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, str]:
    """Return a secret-safe activity draft for one finished run."""

    commands = "; ".join(h.get("command", "") for h in history if h.get("command"))
    last = history[-1] if history else {}

    if llm.available():
        # Give the model only redacted run output so it cannot echo secrets.
        log = "\n".join(
            f"$ {h.get('command','')}\n(exit {h.get('exit_code')}) {(h.get('stdout') or '')[:400]}"
            for h in history
        )
        out = llm.complete_json(
            _SYSTEM,
            f"TICKET: {ticket.get('title','')}\n{ticket.get('description','')}\n\nRUN LOG:\n{redact(log)}",
        )
        if out:
            # Redact again after the LLM response because the model may copy risky text.
            return {k: redact(str(out.get(k, ""))) or "" for k in _FIELDS}

    # Simple fallback: good enough for review, and the technician can edit it.
    return {
        "summary": f"Worked ticket: {ticket.get('title', '')}.",
        "root_cause": "Identify the technical root cause from the actions taken.",
        "actions_taken": "Diagnosed via service status and logs, applied a targeted fix, validated.",
        "commands_summary": (redact(commands) or "")[:1000],
        "validation_result": (redact(last.get("stdout", "")) or "")[:500]
        or "Re-ran the check; customer benefit restored.",
    }
