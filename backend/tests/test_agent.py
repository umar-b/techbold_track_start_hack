"""Spec for the planning agent — LLM path + safe baseline fallback."""
import types

from app import agent

# Small fake ticket/system objects keep the agent tests focused on planning logic.
TICKET = {"id": 7001, "title": "Status API down", "description": "health endpoint unreachable"}
SYS = {"ip": "1.2.3.4", "os": "Ubuntu 22.04"}


def test_baseline_diagnoses_then_finishes_without_llm(monkeypatch):
    """Without an LLM, the agent should use safe diagnostics and then stop."""

    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: None)
    first = agent.propose_action(TICKET, SYS, history=[])
    assert first["action"] == "diagnose" and first["command"]
    # After enough history, the baseline finishes rather than looping forever.
    long_history = [{"command": "x", "exit_code": 0} for _ in range(10)]
    assert agent.propose_action(TICKET, SYS, history=long_history)["action"] == "finish"


def test_uses_llm_action_when_available(monkeypatch):
    """A valid model action should pass through unchanged."""

    plan = {"action": "plan", "root_cause": "nginx not enabled",
            "steps": [{"command": "systemctl enable --now nginx"}], "validation": ["curl -s localhost"]}
    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: plan)
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] == "plan" and out["root_cause"] == "nginx not enabled"


def test_rejects_malformed_llm_output_and_falls_back(monkeypatch):
    """Bad model JSON should not break the run loop."""

    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: {"action": "nonsense"})
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] in {"diagnose", "finish"}  # fell back to baseline


def test_unwraps_nested_action_object(monkeypatch):
    """Some small models nest the action object; the agent should unwrap it."""

    monkeypatch.setattr(agent.llm, "complete_json",
                        lambda *a, **k: {"diagnose": {"action": "diagnose", "command": "uname -a"}})
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] == "diagnose" and out["command"] == "uname -a"


def test_unwraps_action_keyed_wrapper_without_inner_action(monkeypatch):
    """A wrapper key like {'plan': {...}} should become a normal action."""

    monkeypatch.setattr(agent.llm, "complete_json",
                        lambda *a, **k: {"plan": {"root_cause": "x", "steps": []}})
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] == "plan" and out["root_cause"] == "x"


def test_guidebook_loads():
    """The guidebook text should be available for the agent prompt."""

    assert "Persistence" in agent.load_guidebook()
