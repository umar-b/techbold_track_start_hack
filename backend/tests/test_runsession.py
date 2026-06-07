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


def test_reap_idle_sessions_evicts_idle_keeps_fresh(monkeypatch):
    store = _store(monkeypatch)
    old = store.create(7001)
    fresh = store.create(7002)
    s_old = store.session(old, SYSTEM)
    s_fresh = store.session(fresh, SYSTEM)
    # old untouched for ~10 min, fresh touched ~10 s ago (relative to now=1600).
    store._session_last_used[old["id"]] = 1000.0
    store._session_last_used[fresh["id"]] = 1590.0

    reaped = store.reap_idle_sessions(ttl_seconds=300.0, now=1600.0)

    assert reaped == 1
    assert s_old.closed and old["id"] not in store._sessions
    assert not s_fresh.closed and fresh["id"] in store._sessions


def test_reap_skips_session_with_command_in_flight(monkeypatch):
    store = _store(monkeypatch)
    run = store.create(7001)
    s = store.session(run, SYSTEM)
    store._session_last_used[run["id"]] = 0.0
    # A command holds the per-run lock; the reaper must not close mid-command.
    store.lock(run["id"]).acquire()
    try:
        reaped = store.reap_idle_sessions(ttl_seconds=1.0, now=1000.0)
    finally:
        store.lock(run["id"]).release()

    assert reaped == 0 and not s.closed and run["id"] in store._sessions


def test_reap_evicts_session_missing_last_used_stamp(monkeypatch):
    store = _store(monkeypatch)
    run = store.create(7001)
    s = store.session(run, SYSTEM)
    del store._session_last_used[run["id"]]  # a lost stamp must not make it immortal

    reaped = store.reap_idle_sessions(ttl_seconds=300.0, now=10_000.0)

    assert reaped == 1 and s.closed and run["id"] not in store._sessions


def test_reap_disabled_with_nonpositive_ttl(monkeypatch):
    store = _store(monkeypatch)
    run = store.create(7001)
    store.session(run, SYSTEM)
    store._session_last_used[run["id"]] = 0.0
    assert store.reap_idle_sessions(0, now=1e9) == 0


def test_summary_counts_by_status_and_sessions(monkeypatch):
    store = _store(monkeypatch)
    store.create(7001)
    run = store.create(7002)
    store.session(run, SYSTEM)

    summary = store.summary()

    assert summary["total"] == 2
    assert summary["by_status"].get("created") == 2
    assert summary["active_sessions"] == 1
