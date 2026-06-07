"""Spec for the run orchestration API (mocked ERP + SSH + agent; no network)."""
import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app import orchestrator as orch_mod
from app.config import settings
from app.main import create_app, get_phoenix
from app.ssh_runner import CommandResult


class FakePhoenix:
    def __init__(self):
        self.statuses = []
        self.activities = []

    def me(self):
        return {"firstname": "A", "lastname": "B", "teamname": "T"}

    def list_tickets(self, status=None, priority=None, sort="date"):
        return [self.get_ticket(7001)]

    def get_ticket(self, tid):
        return {"id": tid, "title": "Status API down", "description": "health endpoint unreachable",
                "status": "OPEN", "priority": "high", "customer_name": "Nordlicht"}

    def customer_system(self, tid):
        return {"system": {"ip": "1.2.3.4", "port": 22, "username": "azureuser"}}

    def set_status(self, tid, status):
        self.statuses.append((tid, status))
        return {"id": tid, "status": status}

    def create_activity(self, payload):
        self.activities.append(payload)
        return {"id": 1, **payload}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MEMORY_DIR", str(tmp_path / "memory"))
    # Keep tests hermetic: no real LLM/SSH calls even when .env has live creds.
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "")
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("ok", "", 0, 5))
    # Run the background run-loop inline (with the same guard/cleanup) so assertions
    # made right after a POST see the converged state.
    monkeypatch.setattr(orch_mod, "_submit", lambda fn, *a: orch_mod._guarded(fn, *a))
    # The store is a module singleton — isolate each test.
    main_mod.store._runs.clear()
    main_mod.store._audits.clear()
    main_mod.store._sessions.clear()
    main_mod.store._session_last_used.clear()
    fake = FakePhoenix()
    app = create_app()
    app.dependency_overrides[get_phoenix] = lambda: fake
    client = TestClient(app)
    yield client, fake
    app.dependency_overrides.clear()


def _script(monkeypatch, actions):
    it = iter(actions)
    monkeypatch.setattr(orch_mod.agent, "propose_action", lambda *a, **k: next(it))


def test_full_run_diagnose_plan_approve_finish(env, monkeypatch):
    client, fake = env
    _script(monkeypatch, [
        {"action": "diagnose", "command": "systemctl status nginx", "rationale": "check"},
        {"action": "diagnose", "command": "systemctl is-enabled nginx", "rationale": "enabled?"},
        {"action": "plan", "root_cause": "nginx not enabled",
         "steps": [{"command": "systemctl enable --now nginx", "expected": "active"}],
         "validation": ["curl -s http://localhost/health"]},
    ])
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    rid = run["id"]
    assert run["status"] == "awaiting_plan_approval"
    assert run["plan"]["root_cause"] == "nginx not enabled"
    assert (7001, "PENDING") in fake.statuses
    assert len([s for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "executed"]) == 2

    run = client.post(f"/api/runs/{rid}/approve", json={}).json()
    assert run["status"] == "finished"
    fix = [s for s in run["steps"] if s["kind"] == "fix"]
    assert fix and fix[0]["status"] == "executed"
    assert any(s["kind"] == "validate" for s in run["steps"])

    draft = client.get(f"/api/runs/{rid}/activity-draft").json()
    assert "summary" in draft and "root_cause" in draft

    resp = client.post(f"/api/runs/{rid}/submit-activity",
                       json={"summary": "s", "root_cause": "r", "actions_taken": "a",
                             "commands_summary": "c", "validation_result": "v"}).json()
    assert resp["activity"]["ticket_id"] == 7001
    assert (7001, "DONE") in fake.statuses

    # The finished run is persisted to the durable corpus with its full step log.
    runs = client.get("/api/tickets/7001/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["outcome"] == "finished"
    assert runs[0]["counts"]["fixes_executed"] == 1
    assert client.get(f"/api/runs/{rid}/record").json()["id"] == rid


def test_blocked_command_in_approved_plan_never_runs(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x", "steps": [{"command": "rm -rf /"}], "validation": []},
        {"action": "finish", "summary": "done"},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/approve", json={}).json()
    fix = [s for s in run["steps"] if s["kind"] == "fix"][0]
    assert fix["status"] == "blocked" and fix["risk"] == "BLOCKED"
    # blocked fix -> verification fails -> agent re-plans; here it can't, so it escalates
    assert run["status"] == "escalated"


def test_abort_from_plan_gate(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x", "steps": [{"command": "systemctl restart nginx"}],
         "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/abort").json()
    assert run["status"] == "aborted"

    # An aborted attempt is corpus too — persisted so it can be learned from.
    runs = client.get("/api/tickets/7001/runs").json()["runs"]
    assert len(runs) == 1 and runs[0]["outcome"] == "aborted"


def test_get_unknown_run_404(env):
    client, _ = env
    assert client.get("/api/runs/nope").status_code == 404


def test_reject_on_non_awaiting_returns_409(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [{"action": "finish", "summary": "already healthy"}])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    # the run finished during analysis — there is nothing to reject
    assert client.post(f"/api/runs/{rid}/reject", json={}).status_code == 409


def test_start_run_returns_immediately_before_analysis(env, monkeypatch):
    client, _ = env
    # Defer the background loop: the POST must return at once, before diagnostics run.
    monkeypatch.setattr(orch_mod, "_submit", lambda fn, *a: None)
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "analyzing"
    assert run["steps"] == [] and run["plan"] is None


def test_set_plan_keeps_no_plan_when_run_already_aborted():
    # abort-during-analysis race: transition must raise before the plan is written
    from app.runstate import IllegalTransition
    run = {"id": "x", "ticket_id": 7001, "status": "aborted", "steps": [], "plan": None}
    with pytest.raises(IllegalTransition):
        orch_mod._set_plan(run, {"root_cause": "c", "steps": [], "validation": []})
    assert run["plan"] is None


def test_second_concurrent_run_for_ticket_is_rejected(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(orch_mod, "_submit", lambda fn, *a: None)  # leave the first run active
    assert client.post("/api/runs", json={"ticket_id": 7001}).status_code == 200
    assert client.post("/api/runs", json={"ticket_id": 7001}).status_code == 409


def test_unreachable_host_escalates_instead_of_looping(env, monkeypatch):
    client, _ = env
    # Every diagnostic fails (host unreachable) and the agent only ever wants to probe.
    monkeypatch.setattr(orch_mod.agent, "propose_action",
                        lambda *a, **k: {"action": "diagnose", "command": "systemctl status x", "rationale": "probe"})
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("", "unreachable", 1, 5))
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "escalated"
    assert len([s for s in run["steps"] if s["kind"] == "diagnose"]) >= orch_mod.DIAGNOSE_HARD_LIMIT


def test_approve_with_edited_steps_runs_the_edited_command(env, monkeypatch):
    client, _ = env
    ran = []
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None: (ran.append(command), CommandResult("ok", "", 0, 5))[1])
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "x",
         "steps": [{"command": "systemctl restart nginx"}], "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    run = client.post(f"/api/runs/{rid}/approve",
                      json={"steps": [{"command": "systemctl restart apache2", "rationale": "edited"}]}).json()
    fix = [s for s in run["steps"] if s["kind"] == "fix"]
    assert fix and fix[0]["command"] == "systemctl restart apache2"  # the EDITED command ran
    assert "systemctl restart apache2" in ran and "systemctl restart nginx" not in ran


def test_finish_with_no_successful_evidence_escalates(env, monkeypatch):
    client, _ = env
    actions = iter([
        {"action": "diagnose", "command": "systemctl status x", "rationale": "probe"},
        {"action": "finish", "summary": "looks fine"},
    ])
    monkeypatch.setattr(orch_mod.agent, "propose_action", lambda *a, **k: next(actions))
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("", "no route to host", 1, 5))
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "escalated"  # all diagnostics failed -> can't report "resolved"


def test_repeated_gated_diagnostic_does_not_loop(env, monkeypatch):
    client, _ = env
    # Regression: the agent keeps proposing a GATED command (e.g. the validation script) as a
    # "diagnostic". It must NOT spin re-proposing it up to the hard limit — after a couple of
    # rejections the loop forces a plan and (since this stub never plans) escalates. The agent
    # must also RECEIVE its rejected attempts as feedback rather than flying blind.
    seen_rejected = []

    def fake(ticket, system, history, memory="", must_plan=False, rejected=None, force=False, feedback=""):
        seen_rejected.append(len(rejected or []))
        return {"action": "diagnose", "command": "sudo /opt/hackathon/public-test.sh",
                "rationale": "validate first"}

    monkeypatch.setattr(orch_mod.agent, "propose_action", fake)
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()

    assert run["status"] == "escalated"
    diagnoses = [s for s in run["steps"] if s["kind"] == "diagnose"]
    # Converges fast — bounded by REJECTED_DIAGNOSE_LIMIT (+1), well under the hard limit of 10.
    assert len(diagnoses) <= orch_mod.REJECTED_DIAGNOSE_LIMIT + 1
    assert diagnoses and all(s["status"] == "rejected" for s in diagnoses)
    # The agent was told about its earlier rejected attempts (so a real LLM could self-correct).
    assert max(seen_rejected) >= 1


def test_ssh_transport_failure_escalates_without_looping(env, monkeypatch):
    client, _ = env
    # SSH cannot connect (e.g. a missing key). Every diagnostic would fail identically, so the
    # run must escalate on the FIRST transport error (exit_code None) — not loop to the limit.
    from app.ssh_runner import SSHError

    def boom(run, system, command, timeout=None):
        raise SSHError("SSH key not found (looked for ''). Set SSH_PRIVATE_KEY_PATH ...")

    monkeypatch.setattr(orch_mod, "_execute", boom)
    monkeypatch.setattr(orch_mod.agent, "propose_action",
                        lambda *a, **k: {"action": "diagnose", "command": "systemctl status x",
                                         "rationale": "probe"})
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()

    assert run["status"] == "escalated"
    diagnoses = [s for s in run["steps"] if s["kind"] == "diagnose"]
    assert len(diagnoses) == 1  # escalated on the first transport error — no loop
    assert (diagnoses[0]["result"] or {}).get("exit_code") is None
    assert "SSH key" in (diagnoses[0]["result"] or {}).get("stderr", "")


def test_tickets_proxy(env):
    client, _ = env
    assert client.get("/api/tickets").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


def test_runs_list_and_stats_endpoints(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "nginx down",
         "steps": [{"command": "systemctl enable --now nginx"}], "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]

    listed = client.get("/api/runs").json()
    row = next(x for x in listed if x["id"] == rid)
    assert row["ticket_id"] == 7001
    assert row["status"] == "awaiting_plan_approval"
    assert isinstance(row["steps"], int) and "created_at" in row

    stats = client.get("/api/stats").json()
    assert stats["total"] >= 1
    assert sum(stats["by_status"].values()) == stats["total"]
    assert "active_sessions" in stats


def test_audit_trail_endpoint_returns_redacted_entries(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "nginx down",
         "steps": [{"command": "systemctl enable --now nginx"}], "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]

    body = client.get(f"/api/runs/{rid}/audit").json()
    assert body["run_id"] == rid
    events = [e["event"] for e in body["entries"]]
    assert "run_started" in events and "plan_proposed" in events
    assert all("ts" in e for e in body["entries"])

    assert client.get("/api/runs/nope/audit").status_code == 404


def test_reject_with_feedback_steers_the_replan(env, monkeypatch):
    client, _ = env
    seen = {}
    actions = iter([
        {"action": "plan", "root_cause": "a",
         "steps": [{"command": "systemctl restart nginx"}], "validation": []},
        {"action": "plan", "root_cause": "b",
         "steps": [{"command": "systemctl reload nginx"}], "validation": []},
    ])

    def fake(*a, **k):
        seen.clear()
        seen.update(k)
        return next(actions)

    monkeypatch.setattr(orch_mod.agent, "propose_action", fake)
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]

    run = client.post(f"/api/runs/{rid}/reject", json={"feedback": "reload, don't restart"}).json()

    assert run["status"] == "awaiting_plan_approval"
    assert seen.get("feedback") == "reload, don't restart"  # the steer reached the agent
    assert run["plan"]["root_cause"] == "b"


def test_memory_endpoint_lists_notes(env):
    client, _ = env
    from app import memory as mem
    mem.write_note(
        {"id": "r1", "ticket_id": 7001, "created_at": "2026-06-06T10:00:00Z",
         "steps": [{"kind": "fix", "command": "systemctl enable --now nginx", "status": "executed"}]},
        {"id": 7001, "title": "nginx down", "description": "502"},
        {"root_cause": "not enabled", "validation_result": "ok"}, {"os": "Ubuntu"})
    body = client.get("/api/memory").json()
    assert any(n["id"].startswith("ticket7001") for n in body["notes"])


def test_start_run_reports_memory_seed_count(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(orch_mod.agent, "propose_action", lambda *a, **k: {"action": "finish", "summary": "ok"})
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run.get("memory_count") == 0  # tmp memory dir is empty


def test_submit_activity_is_readable_per_ticket(env, monkeypatch):
    client, _ = env
    _script(monkeypatch, [
        {"action": "plan", "root_cause": "nginx down",
         "steps": [{"command": "systemctl enable --now nginx"}], "validation": []},
    ])
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    client.post(f"/api/runs/{rid}/approve", json={})
    client.post(f"/api/runs/{rid}/submit-activity",
                json={"summary": "Restored nginx", "root_cause": "unit was disabled",
                      "actions_taken": "enabled the unit", "commands_summary": "systemctl enable --now nginx",
                      "validation_result": "HTTP 200"})

    body = client.get("/api/tickets/7001/activities").json()
    assert body["ticket_id"] == 7001
    assert body["activities"] and body["activities"][0]["summary"] == "Restored nginx"
    assert body["activities"][0]["root_cause"] == "unit was disabled"


def test_endless_safe_diagnostics_are_forced_to_a_decision(env, monkeypatch):
    # A model that keeps probing read-only forever must be forced to a decision and
    # escalate, NOT burn every attempt (regression: ticket 7005 — 9 probes, no plan).
    client, _ = env
    monkeypatch.setattr(orch_mod.agent, "propose_action",
                        lambda *a, **k: {"action": "diagnose", "command": "systemctl status x", "rationale": "probe"})
    run = client.post("/api/runs", json={"ticket_id": 7001}).json()
    assert run["status"] == "escalated"
    executed = [s for s in run["steps"] if s["kind"] == "diagnose" and s["status"] == "executed"]
    assert len(executed) <= orch_mod.DIAGNOSE_FORCE_LIMIT  # bounded; never reaches the hard limit


def test_repeated_failed_fix_escalates_after_max_attempts(env, monkeypatch):
    # The agent keeps proposing plans whose validation fails. It must escalate after
    # MAX_FIX_ATTEMPTS rather than replanning forever (regression: ticket 7005 — ~6 cycles).
    client, _ = env
    monkeypatch.setattr(orch_mod.agent, "propose_action",
                        lambda *a, **k: {"action": "plan", "root_cause": "x",
                                         "steps": [{"command": "systemctl restart svc"}],
                                         "validation": ["sudo /opt/hackathon/public-test.sh"]})
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None: CommandResult("", "still failing", 1, 5))
    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    for _ in range(orch_mod.MAX_FIX_ATTEMPTS + 3):
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] != "awaiting_plan_approval":
            break
        client.post(f"/api/runs/{rid}/approve", json={})

    final = client.get(f"/api/runs/{rid}").json()
    assert final["status"] == "escalated"
    fixes = [s for s in final["steps"] if s["kind"] == "fix"]
    assert 0 < len(fixes) <= orch_mod.MAX_FIX_ATTEMPTS


def test_replan_can_diagnose_before_proposing_a_new_plan(env, monkeypatch):
    # Regression (ticket 7005, run ed3aa58): after a fix fails validation, the agent must be
    # able to FIRST diagnose why, then propose a better plan — not escalate on the first
    # non-plan response.
    actions = iter([
        {"action": "plan", "root_cause": "first guess",
         "steps": [{"command": "systemctl enable --now svc-a"}],
         "validation": ["sudo /opt/hackathon/public-test.sh"]},
        {"action": "diagnose", "command": "journalctl -u svc-a -n 20 --no-pager", "rationale": "why failed"},
        {"action": "plan", "root_cause": "second guess",
         "steps": [{"command": "systemctl enable --now svc-b"}], "validation": []},
    ])
    monkeypatch.setattr(orch_mod.agent, "propose_action", lambda *a, **k: next(actions))
    monkeypatch.setattr(orch_mod, "_execute",
                        lambda run, system, command, timeout=None:
                        CommandResult("out", "", 1 if "public-test" in command else 0, 5))
    client, _ = env

    rid = client.post("/api/runs", json={"ticket_id": 7001}).json()["id"]
    first = client.get(f"/api/runs/{rid}").json()
    assert first["status"] == "awaiting_plan_approval" and first["plan"]["root_cause"] == "first guess"

    after = client.post(f"/api/runs/{rid}/approve", json={}).json()
    assert after["status"] == "awaiting_plan_approval"
    assert after["plan"]["root_cause"] == "second guess"  # replan produced a NEW plan
    assert any(s["kind"] == "diagnose" and "journalctl" in s["command"] for s in after["steps"])
