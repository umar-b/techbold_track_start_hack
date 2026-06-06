"""Single planning agent (ADR-0003, ADR-0007).

Proposes the next action given the ticket, the customer system, and the history
of executed commands. One of:

  diagnose - ONE read-only command to gather evidence (auto-runs as SAFE)
  plan     - a root cause + ordered fix steps for the technician to approve
  finish   - validated; nothing more to do

The agent reasons over live evidence using the guidebook method (no hard-coded
recipes) and emits a JSON action (ADR-0010: JSON mode, not native tools). Without
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
- Each diagnose step is ONE plain command (e.g. `systemctl status nginx`, `ss -tlnp`). Do NOT
  wrap commands in `bash -lc`, `sh -c`, or `eval` — plain read-only commands run immediately,
  wrapped ones must wait for manual approval. `sudo` is fine and available (passwordless).
- `diagnose` is READ-ONLY. Any command that changes state (restart/start/enable/edit/install/
  chown/chmod) MUST go in a `plan`, never in a diagnose step.
- Converge: after 2–4 diagnostics that localise the cause, propose a `plan`. Do not diagnose
  indefinitely. Choose `finish` ONLY when the evidence shows the issue is resolved (the symptom
  is gone or the validation/`public-test.sh` passes) — never while the reported problem is still
  failing or unverified.

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
            "summary": "Baseline diagnostics complete (configure an LLM provider for full reasoning)."}


def _unwrap(out: Any) -> Any:
    """nano sometimes nests the action object (e.g. {"diagnose": {...}}); unwrap it."""
    if not isinstance(out, dict):
        return out
    if out.get("action") in _ACTIONS:
        return out
    for key, value in out.items():
        if isinstance(value, dict):
            if value.get("action") in _ACTIONS:
                return value
            if key in _ACTIONS:  # {"plan": {...}} with no inner "action"
                return {**value, "action": key}
    return out


def propose_action(ticket: Dict[str, Any], system: Dict[str, Any],
                   history: List[Dict[str, Any]], memory: str = "",
                   must_plan: bool = False, model: Any = None) -> Dict[str, Any]:
    related = ("RELATED PAST INCIDENTS (verify against live evidence, do not assume):\n" + memory) if memory else ""
    closing = (
        "You now have enough evidence. Respond with action=plan — an ordered list of fix steps "
        "plus validation commands. Use action=finish ONLY if the system is already healthy and "
        "needs no change. Do NOT diagnose further."
        if must_plan else
        "Propose the next single action as JSON: diagnose while still investigating, otherwise plan."
    )
    user = (
        f"GUIDEBOOK:\n{load_guidebook()}\n\n"
        f"TICKET #{ticket.get('id')}: {ticket.get('title','')}\n{ticket.get('description','')}\n\n"
        f"SYSTEM: {system}\n\n{related}\n\n"
        f"HISTORY:\n{_history_text(history)}\n\n{closing}"
    )
    # All in-loop reasoning — both deciding the next diagnostic and producing the
    # plan — runs on the stronger reasoning model (ADR-0011). The cheap model is
    # reserved for non-reasoning text (the activity-log draft).
    out = _unwrap(llm.complete_json(_SYSTEM, user, model=model, reasoning=True))
    if isinstance(out, dict) and out.get("action") in _ACTIONS:
        return out
    return _baseline(history)
