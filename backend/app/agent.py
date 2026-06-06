"""Single planning agent (ADR-0003, ADR-0007).

Proposes the next action given the ticket, the customer system, and the history
of executed commands. One of:

  diagnose - ONE read-only command to gather evidence (auto-runs as SAFE)
  plan     - a root cause + ordered fix steps for the technician to approve
  finish   - validated; nothing more to do

The agent reasons over live evidence using the guidebook method (no hard-coded
recipes). Without an LLM it falls back to a safe read-only baseline so the loop
always runs. Memory may pre-fill the plan as hypotheses-to-verify (ADR-0009),
never as actions-to-apply.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from . import llm

_GUIDEBOOK_PATH = Path(__file__).resolve().parent / "guidebook.md"
_ACTIONS = {"diagnose", "plan", "finish"}

_SYSTEM = """You are an expert Linux technician's AI copilot resolving ONE incident on a customer VM.
A human approves every change — you propose, you never act unsupervised.

Method: gather read-only evidence -> rank hypotheses with their evidence -> test the cheapest
first -> propose the SMALLEST fix that addresses the ROOT CAUSE (not the symptom) -> validate.

Hard rules:
- Prefer PERSISTENT fixes: a service must be enabled (systemctl enable --now), config written to
  disk, fstab/firewall rules persisted. A fix that dies on reboot is not done.
- Minimal change. Never run destructive blanket commands. Never reinitialise a database or
  remove customer data. Never reconfigure the app to run as a DB superuser. Never read secrets
  (/etc/shadow, *.env, private keys).
- Validate with the provided test when present: `sudo /opt/hackathon/public-test.sh`.

Respond by calling propose_action with EXACTLY one action:
- diagnose: one read-only `command` + short `rationale` (while still investigating)
- plan: `root_cause`, ordered `steps` (each: command, rationale, expected), and `validation` commands
- finish: a one-line `summary` once validated.
"""

_ACTION_TOOL = {
    "name": "propose_action",
    "description": "Propose the single next action in the troubleshooting loop.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["diagnose", "plan", "finish"]},
            "command": {"type": "string", "description": "diagnose: one read-only shell command"},
            "rationale": {"type": "string"},
            "root_cause": {"type": "string", "description": "plan: the technical root cause"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "rationale": {"type": "string"},
                        "expected": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
            "validation": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": ["action"],
    },
}

# Read-only baseline so the workflow runs without an LLM (ADR-0004 graceful degradation).
_BASELINE: List[Dict[str, str]] = [
    {"command": "systemctl --failed --no-pager", "rationale": "List failed services first."},
    {"command": "journalctl -p err -n 80 --no-pager", "rationale": "Recent error-level logs."},
    {"command": "df -h", "rationale": "Check for a full filesystem."},
    {"command": "ss -tlnp", "rationale": "See which services are listening."},
]


def load_guidebook() -> str:
    try:
        return _GUIDEBOOK_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _history_text(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "(nothing run yet)"
    lines = []
    for h in history[-12:]:
        out = (h.get("stdout") or "")[:600]
        err = (h.get("stderr") or "")[:200]
        lines.append(f"$ {h.get('command','')}\n(exit {h.get('exit_code')}) {out} {err}".strip())
    return "\n".join(lines)


def _baseline(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    i = len(history)
    if i < len(_BASELINE):
        step = _BASELINE[i]
        return {"action": "diagnose", "command": step["command"], "rationale": step["rationale"]}
    return {"action": "finish",
            "summary": "Baseline diagnostics complete (configure Azure OpenAI for full reasoning)."}


def propose_action(ticket: Dict[str, Any], system: Dict[str, Any],
                   history: List[Dict[str, Any]], memory: str = "",
                   client: Any = None) -> Dict[str, Any]:
    user = (
        f"GUIDEBOOK:\n{load_guidebook()}\n\n"
        f"TICKET #{ticket.get('id')}: {ticket.get('title','')}\n{ticket.get('description','')}\n\n"
        f"SYSTEM: {system}\n\n"
        f"{('RELATED PAST INCIDENTS (verify against live evidence, do not assume):' + chr(10) + memory) if memory else ''}\n\n"
        f"HISTORY:\n{_history_text(history)}\n\nPropose the next single action."
    )
    out = llm.complete_json(_SYSTEM, user, tool=_ACTION_TOOL, client=client)
    if isinstance(out, dict) and out.get("action") in _ACTIONS:
        return out
    return _baseline(history)
