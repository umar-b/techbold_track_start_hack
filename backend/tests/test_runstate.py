"""Spec for the Run phase machine (legal vs illegal transitions)."""
import pytest

from app.runstate import IllegalTransition, RunStatus, is_terminal, transition


def _run(status):
    return {"status": status}


def test_legal_happy_path_transitions():
    run = _run("created")
    transition(run, RunStatus.ANALYZING)
    assert run["status"] == "analyzing"
    transition(run, RunStatus.AWAITING_PLAN_APPROVAL)
    transition(run, RunStatus.EXECUTING)
    transition(run, RunStatus.VERIFYING)
    transition(run, RunStatus.FINISHED)
    assert run["status"] == "finished"


def test_replan_loop_is_legal():
    run = _run("verifying")
    transition(run, RunStatus.ANALYZING)  # failed verification -> replan
    transition(run, RunStatus.AWAITING_PLAN_APPROVAL)
    assert run["status"] == "awaiting_plan_approval"


def test_abort_allowed_from_any_non_terminal():
    for s in ("created", "analyzing", "awaiting_plan_approval", "executing", "verifying"):
        run = _run(s)
        transition(run, RunStatus.ABORTED)
        assert run["status"] == "aborted"


def test_illegal_transition_raises():
    with pytest.raises(IllegalTransition):
        transition(_run("created"), RunStatus.FINISHED)
    with pytest.raises(IllegalTransition):
        transition(_run("awaiting_plan_approval"), RunStatus.VERIFYING)


def test_no_transition_out_of_terminal():
    with pytest.raises(IllegalTransition):
        transition(_run("finished"), RunStatus.ANALYZING)


def test_noop_transition_is_allowed():
    run = _run("analyzing")
    transition(run, RunStatus.ANALYZING)
    assert run["status"] == "analyzing"


def test_reject_replan_edge_is_legal():
    # reject route: awaiting_plan_approval -> _replan -> analyzing -> new plan
    run = _run("awaiting_plan_approval")
    transition(run, RunStatus.ANALYZING)
    transition(run, RunStatus.AWAITING_PLAN_APPROVAL)
    assert run["status"] == "awaiting_plan_approval"


def test_is_terminal():
    assert is_terminal("finished") and is_terminal("aborted") and is_terminal("escalated")
    assert not is_terminal("analyzing")
    assert not is_terminal("bogus")
