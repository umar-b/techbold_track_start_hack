"""Explicit Run phase machine — the seam for status legality.

Run statuses used to be bare string literals set in ~9 places with a single
ad-hoc guard. This concentrates phase legality: every status change goes through
`transition()`, which raises `IllegalTransition` on an illegal edge so a wrong
move fails loud instead of silently leaving a run in an impossible state.

The string values match the wire contract the frontend reads (frontend/src/types.ts).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Set


class RunStatus(str, Enum):
    CREATED = "created"
    ANALYZING = "analyzing"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    FINISHED = "finished"
    ESCALATED = "escalated"
    ABORTED = "aborted"


TERMINAL: Set[RunStatus] = {RunStatus.FINISHED, RunStatus.ESCALATED, RunStatus.ABORTED}

# Allowed forward edges. Abort (technician) is allowed from any non-terminal
# status and is added to every non-terminal entry below.
_TRANSITIONS: Dict[RunStatus, Set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.ANALYZING},
    RunStatus.ANALYZING: {RunStatus.AWAITING_PLAN_APPROVAL, RunStatus.FINISHED, RunStatus.ESCALATED},
    RunStatus.AWAITING_PLAN_APPROVAL: {RunStatus.EXECUTING, RunStatus.ANALYZING},
    RunStatus.EXECUTING: {RunStatus.VERIFYING},
    RunStatus.VERIFYING: {RunStatus.FINISHED, RunStatus.ANALYZING, RunStatus.ESCALATED},
    RunStatus.FINISHED: set(),
    RunStatus.ESCALATED: set(),
    RunStatus.ABORTED: set(),
}
for _status, _allowed in _TRANSITIONS.items():
    if _status not in TERMINAL:
        _allowed.add(RunStatus.ABORTED)


class IllegalTransition(RuntimeError):
    pass


def is_terminal(status: str) -> bool:
    try:
        return RunStatus(status) in TERMINAL
    except ValueError:
        return False


def transition(run: Dict[str, Any], target: RunStatus) -> None:
    """Move `run` to `target`, raising IllegalTransition on an illegal edge.

    A no-op (target == current) is allowed. Mutates run["status"] in place, the
    one place a status write happens.
    """
    current = RunStatus(run["status"])
    if target == current:
        return
    if target not in _TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"illegal run transition: {current.value} -> {target.value}")
    run["status"] = target.value
