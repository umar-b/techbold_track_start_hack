"""Spec for the command safety layer (ADR-0002, ADR-0004).

Risk tiers:
  SAFE    - non-mutating reads; may auto-run.
  GATED   - state-changing; only inside an approved plan.
  BLOCKED - dangerous / secret-exposing; never runs.
"""
import pytest

from app.safety import RiskTier, check_command


def tier(cmd: str) -> RiskTier:
    return check_command(cmd).tier


@pytest.mark.parametrize("cmd", [
    "uname -a",
    "df -h",
    "free -m",
    "ls -la /var/www",
    "cat /etc/nginx/nginx.conf",
    "systemctl status nginx",
    "systemctl is-enabled nginx",
    "journalctl -u nginx -n 50 --no-pager",
    "ss -tlnp",
    "ps aux",
    "grep -r error /var/log/app",
    "curl -s http://localhost:8080/health",
    "id",
    "getent hosts partner-api.internal",
    "sudo systemctl status postgresql",
    "cat /etc/hosts && ss -tlnp",
    "find /var/www -name '*.conf'",
])
def test_safe_reads(cmd):
    assert tier(cmd) is RiskTier.SAFE


@pytest.mark.parametrize("cmd", [
    "systemctl restart nginx",
    "systemctl enable --now nginx",
    "chown -R app:app /var/www/app/uploads",
    "chmod 644 /var/www/app/uploads/file",
    "apt-get install -y nginx",
    "sed -i 's/x/y/' /etc/nginx/nginx.conf",
    "echo '127.0.0.1 partner-api.internal' >> /etc/hosts",
    "kill 1234",
    "systemctl restart postgresql",
    "rm /var/www/app/cache/tmpfile",
    "curl -X POST http://localhost:8080/reload",
])
def test_gated_mutations(cmd):
    assert tier(cmd) is RiskTier.GATED


@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "rm -rf /etc",
    "sudo rm -rf /var",
    "chmod -R 777 /",
    "chmod -R 777 /etc",
    "sudo chmod -R 777 /var",
    "chown -R nobody /etc",
    "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda",
    "dropdb orders",
    "psql -c 'DROP DATABASE orders'",
    "truncate table orders",
    "systemctl stop ufw",
    "ufw disable",
    "systemctl disable sshd",
    "history -c",
    "rm -rf /var/lib/postgresql",
    "rm -rf /var/log",
    ":(){ :|:& };:",
])
def test_blocked_dangerous(cmd):
    assert tier(cmd) is RiskTier.BLOCKED


@pytest.mark.parametrize("cmd", [
    "cat /etc/shadow",
    "sudo cat /etc/shadow",
    "cat ~/.ssh/id_rsa",
    "cat /opt/app/.env",
    "grep PASSWORD /srv/app/.env",
    "cat /etc/ssh/ssh_host_rsa_key",
    "head -5 /home/azureuser/server.pem",
])
def test_secret_reads_blocked(cmd):
    assert tier(cmd) is RiskTier.BLOCKED


def test_sudo_prefix_does_not_bypass_block():
    assert check_command("sudo rm -rf /").tier is RiskTier.BLOCKED


def test_targeted_chown_on_upload_dir_is_gated_not_blocked():
    # The rubric's explicit example: a targeted chown on an upload dir is fine.
    assert check_command("chown -R www-data:www-data /var/www/portal/uploads").tier is RiskTier.GATED


def test_empty_command_blocked():
    assert check_command("   ").tier is RiskTier.BLOCKED


def test_allowed_convenience_flag():
    assert check_command("uname -a").allowed is True
    assert check_command("rm -rf /").allowed is False
