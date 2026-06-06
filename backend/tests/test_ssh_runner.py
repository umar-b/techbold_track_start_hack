"""Spec for SSH key resolution (single-key vs per-VM caseN convention). No network."""
from app import ssh_runner
from app.config import settings


def test_explicit_existing_key_wins(tmp_path, monkeypatch):
    key = tmp_path / "my.pem"
    key.write_text("x")
    monkeypatch.setattr(settings, "SSH_PRIVATE_KEY_PATH", str(key))
    assert ssh_runner.resolve_key_path(7001) == str(key)


def test_per_vm_case_key_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SSH_PRIVATE_KEY_PATH", "/nonexistent/none.pem")
    monkeypatch.setattr(settings, "SSH_KEY_DIR", str(tmp_path))
    (tmp_path / "case2_key.pem").write_text("x")
    assert ssh_runner.resolve_key_path(7002).endswith("case2_key.pem")
