"""Spec for SSH key resolution (single-key vs per-VM caseN convention). No network."""
import pytest

from app import ssh_runner
from app.config import settings


def test_explicit_existing_key_wins(tmp_path, monkeypatch):
    """A configured key path should win when the file exists."""

    key = tmp_path / "my.pem"
    key.write_text("x")
    monkeypatch.setattr(settings, "SSH_PRIVATE_KEY_PATH", str(key))
    assert ssh_runner.resolve_key_path(7001) == str(key)


def test_per_vm_case_key_fallback(tmp_path, monkeypatch):
    """If the shared key is missing, use the caseN key for that ticket."""

    monkeypatch.setattr(settings, "SSH_PRIVATE_KEY_PATH", "/nonexistent/none.pem")
    monkeypatch.setattr(settings, "SSH_KEY_DIR", str(tmp_path))
    (tmp_path / "case2_key.pem").write_text("x")
    assert ssh_runner.resolve_key_path(7002).endswith("case2_key.pem")


def test_load_key_missing_path_gives_actionable_error():
    """A missing key file raises a clear SSHError naming SSH_PRIVATE_KEY_PATH, not a stack trace."""
    with pytest.raises(ssh_runner.SSHError) as ei:
        ssh_runner._load_key("/nope/missing.pem", None)
    assert "SSH_PRIVATE_KEY_PATH" in str(ei.value)


def test_resolve_key_path_missing_names_concrete_case_file(tmp_path, monkeypatch):
    """For ticket 7001 the error names case1_key.pem concretely — no 'ticket id - 7000' formula."""
    monkeypatch.setattr(settings, "SSH_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "SSH_KEY_DIR", str(tmp_path))
    with pytest.raises(ssh_runner.SSHError) as ei:
        ssh_runner.resolve_key_path(7001)
    msg = str(ei.value)
    assert "case1_key.pem" in msg
    assert "SSH_PRIVATE_KEY_PATH" in msg
