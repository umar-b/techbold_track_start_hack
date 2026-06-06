"""Spec for secret redaction + the append-only audit log (ADR-0004, ADR-0008)."""
from app.audit import AuditLog, redact


def test_redacts_private_key_block():
    text = "before -----BEGIN OPENSSH PRIVATE KEY-----\nSECRETBODY\n-----END OPENSSH PRIVATE KEY----- after"
    out = redact(text)
    assert "SECRETBODY" not in out and "[REDACTED_PRIVATE_KEY]" in out


def test_redacts_password_and_token_assignments():
    assert redact("PASSWORD=hunter2") == "PASSWORD=[REDACTED]"
    assert "[REDACTED]" in redact("api_key: sk-abc123")
    assert "[REDACTED]" in redact("db_secret=topsecret")


def test_redacts_bearer_header():
    assert "[REDACTED]" in redact("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in redact("Authorization: Bearer abc.def.ghi")


def test_redacts_connection_uri_password():
    out = redact("postgres://appuser:s3cretpw@db:5432/app")
    assert "s3cretpw" not in out and "appuser" in out


def test_non_string_passes_through():
    assert redact(None) is None
    assert redact("") == ""


def test_auditlog_appends_redacts_and_persists(tmp_path):
    log = AuditLog("run1", persist_dir=str(tmp_path))
    log.add("command_executed", command="cat /etc/hosts", exit_code=0)
    log.add("note", detail="leaked PASSWORD=hunter2 here")

    entries = log.entries
    assert len(entries) == 2
    assert entries[0]["event"] == "command_executed" and entries[0]["exit_code"] == 0
    assert "[REDACTED]" in entries[1]["detail"]  # string fields are redacted

    persisted = tmp_path / "run1.jsonl"
    assert persisted.exists() and persisted.read_text().count("\n") == 2


def test_entries_returns_a_copy():
    log = AuditLog("run2")
    log.add("x")
    snapshot = log.entries
    snapshot.append({"event": "tamper"})
    assert len(log.entries) == 1  # append-only; external mutation can't grow it
