"""Spec for the planning agent — LLM path + safe baseline fallback."""
import types

from app import agent

TICKET = {"id": 7001, "title": "Status API down", "description": "health endpoint unreachable"}
SYS = {"ip": "1.2.3.4", "os": "Ubuntu 22.04"}


def test_baseline_diagnoses_then_finishes_without_llm(monkeypatch):
    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: None)
    first = agent.propose_action(TICKET, SYS, history=[])
    assert first["action"] == "diagnose" and first["command"]
    # After enough history, the baseline finishes rather than looping forever.
    long_history = [{"command": "x", "exit_code": 0} for _ in range(10)]
    assert agent.propose_action(TICKET, SYS, history=long_history)["action"] == "finish"


def test_uses_llm_action_when_available(monkeypatch):
    plan = {"action": "plan", "root_cause": "nginx not enabled",
            "steps": [{"command": "systemctl enable --now nginx"}], "validation": ["curl -s localhost"]}
    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: plan)
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] == "plan" and out["root_cause"] == "nginx not enabled"


def test_rejects_malformed_llm_output_and_falls_back(monkeypatch):
    monkeypatch.setattr(agent.llm, "complete_json", lambda *a, **k: {"action": "nonsense"})
    out = agent.propose_action(TICKET, SYS, history=[])
    assert out["action"] in {"diagnose", "finish"}  # fell back to baseline


def test_guidebook_loads():
    assert "Persistence" in agent.load_guidebook()
