"""Single planning agent (ADR-0003, ADR-0007).

Proposes the next action given the ticket, the customer system, and the history
of executed commands. One of:

  diagnose - ONE read-only command to gather evidence (auto-runs as SAFE)
  plan     - a root cause + ordered fix steps for the technician to approve
  finish   - validated; nothing more to do

The agent reasons over live evidence using the guidebook method (no hard-coded
recipes) and emits a JSON action (ADR-0006: JSON mode, not native tools). Without
an LLM it falls back to a safe read-only baseline so the loop always runs. Memory
may pre-fill the plan as hypotheses-to-verify (ADR-0009), never actions-to-apply.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

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
- Minimal change. Never destructive blanket commands. Never reinitialise a database or remove
  customer data. Never reconfigure the app to run as a DB superuser. Never read secrets
  (/etc/shadow, *.env, private keys).
- Validate with the provided test when present: `sudo /opt/hackathon/public-test.sh`.

Respond ONLY with a single JSON object. Include just the keys for the chosen action:
- diagnose: {"action":"diagnose","command":"<one read-only shell command>","rationale":"<why>"}
- plan: {"action":"plan","root_cause":"<technical cause>","steps":[{"command":"<cmd>","rationale":"<why>","expected":"<expected>"}],"validation":["<check command>"]}
- finish: {"action":"finish","summary":"<one line of what was restored>"}
"""

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
    related = ("RELATED PAST INCIDENTS (verify against live evidence, do not assume):\n" + memory) if memory else ""
    user = (
        f"GUIDEBOOK:\n{load_guidebook()}\n\n"
        f"TICKET #{ticket.get('id')}: {ticket.get('title','')}\n{ticket.get('description','')}\n\n"
        f"SYSTEM: {system}\n\n{related}\n\n"
        f"HISTORY:\n{_history_text(history)}\n\n"
        f"Propose the next single action as JSON."
    )
    out = llm.complete_json(_SYSTEM, user, client=client)
    if isinstance(out, dict) and out.get("action") in _ACTIONS:
        return out
    return _baseline(history)
