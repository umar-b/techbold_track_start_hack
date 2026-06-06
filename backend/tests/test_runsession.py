"""Spec for the run-owned SSH session in the store (no network — fake runner)."""
from app import runstore as rs

SYSTEM = {"ip": "1.2.3.4", "port": 22, "username": "azureuser"}


class FakeRunner:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connects = 0
        self.closed = False
        FakeRunner.instances.append(self)

    def ensure_connected(self):
        self.connects += 1
        return self

    def __exit__(self, *exc):
        self.closed = True


def _store(monkeypatch):
    FakeRunner.instances = []
    monkeypatch.setattr(rs, "SSHRunner", FakeRunner)
    return rs.RunStore()


def test_session_is_created_once_and_reused(monkeypatch):
    store = _store(monkeypatch)
    run = store.create(7001)
    a = store.session(run, SYSTEM)
    b = store.session(run, SYSTEM)
    assert a is b                       # one connection per run, reused
    assert len(FakeRunner.instances) == 1
    assert a.connects == 2              # ensure_connected called on each access (reconnect-if-dropped)


def test_close_session_exits_and_allows_recreate(monkeypatch):
    store = _store(monkeypatch)
    run = store.create(7001)
    first = store.session(run, SYSTEM)
    store.close_session(run["id"])
    assert first.closed
    second = store.session(run, SYSTEM)
    assert second is not first          # a fresh connection after close
    assert len(FakeRunner.instances) == 2


def test_close_unknown_session_is_noop(monkeypatch):
    store = _store(monkeypatch)
    store.close_session("does-not-exist")  # must not raise
