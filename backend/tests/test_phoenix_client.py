"""Spec for the Phoenix ERP client — auth, retries, error mapping (mocked, no network)."""
import httpx
import pytest

from app.phoenix_client import PhoenixClient, PhoenixError


def make_client(handler, retries=2):
    return PhoenixClient(base_url="http://erp.test", token="tok", retries=retries,
                         backoff=0.0, transport=httpx.MockTransport(handler))


def test_lists_tickets_with_bearer_and_query():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("authorization")
        seen["url"] = str(req.url)
        return httpx.Response(200, json=[{"id": 7001, "title": "x"}])

    tickets = make_client(handler).list_tickets(status="OPEN", sort="priority")
    assert tickets[0]["id"] == 7001
    assert seen["auth"] == "Bearer tok"
    assert "status=OPEN" in seen["url"] and "sort=priority" in seen["url"]


def test_404_raises_and_is_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(404, json={"detail": "nope"})

    with pytest.raises(PhoenixError):
        make_client(handler).get_ticket(9999)
    assert calls["n"] == 1  # client errors are surfaced, never retried


def test_5xx_is_retried_then_raises():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    with pytest.raises(PhoenixError):
        make_client(handler, retries=2).me()
    assert calls["n"] == 3  # 1 try + 2 retries


def test_status_and_activity_use_correct_verbs_and_paths():
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path))
        return httpx.Response(200, json={"ok": True})

    c = make_client(handler)
    c.set_status(7001, "DONE")
    c.create_activity({"ticket_id": 7001})
    assert ("PATCH", "/api/v1/tickets/7001/status") in seen
    assert ("POST", "/api/v1/activities/create") in seen


def test_customer_system_path():
    def handler(req):
        return httpx.Response(200, json={"ticket_id": 7001, "system": {"ip": "1.2.3.4"}})

    out = make_client(handler).customer_system(7001)
    assert out["system"]["ip"] == "1.2.3.4"
