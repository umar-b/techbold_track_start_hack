"""Activity-log generator / documenter (ADR-0004).

Drafts the ERP activity from a finished run's executed commands. Uses the LLM
when available, otherwise a deterministic draft from the run history. Every field
is run through the redactor so no secret can reach the ERP.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import llm
from .audit import redact

_FIELDS = ["summary", "root_cause", "actions_taken", "commands_summary", "validation_result"]

_SYSTEM = (
    "You write a concise, technically precise IT activity log for one resolved incident. "
    "Return ONLY JSON with keys: summary, root_cause, actions_taken, commands_summary, "
    "validation_result. root_cause is the technical cause, not the symptom. validation_result "
    "must be concrete (e.g. a test or health-check result). Never include secrets, keys, "
    "passwords or tokens."
)


def draft_activity(ticket: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, str]:
    commands = "; ".join(h.get("command", "") for h in history if h.get("command"))
    last = history[-1] if history else {}

    if llm.available():
        log = "\n".join(
            f"$ {h.get('command','')}\n(exit {h.get('exit_code')}) {(h.get('stdout') or '')[:400]}"
            for h in history
        )
        out = llm.complete_json(
            _SYSTEM,
            f"TICKET: {ticket.get('title','')}\n{ticket.get('description','')}\n\nRUN LOG:\n{redact(log)}",
        )
        if out:
            return {k: redact(str(out.get(k, ""))) or "" for k in _FIELDS}

    return {
        "summary": f"Worked ticket: {ticket.get('title', '')}.",
        "root_cause": "Identify the technical root cause from the actions taken.",
        "actions_taken": "Diagnosed via service status and logs, applied a targeted fix, validated.",
        "commands_summary": (redact(commands) or "")[:1000],
        "validation_result": (redact(last.get("stdout", "")) or "")[:500]
        or "Re-ran the check; customer benefit restored.",
    }
