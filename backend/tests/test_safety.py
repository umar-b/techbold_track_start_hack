"""Spec for the command safety layer (ADR-0002, ADR-0004).

Risk tiers:
  SAFE    - non-mutating reads; may auto-run.
  GATED   - state-changing; only inside an approved plan.
  BLOCKED - dangerous / secret-exposing; never runs.
"""
import pytest

from app.safety import RiskTier, check_command


def tier(cmd: str) -> RiskTier:
    """Return only the tier so parametrized tests stay short."""

    return check_command(cmd).tier


# Read-only commands may run automatically as diagnostics.
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
    """Common Linux inspection commands should be SAFE."""

    assert tier(cmd) is RiskTier.SAFE


# State-changing commands need technician approval inside a plan.
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
    """Useful fix commands should be GATED, not blocked outright."""

    assert tier(cmd) is RiskTier.GATED


# These commands match the case safety hard-fail examples.
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
    """Dangerous blanket operations must never run."""

    assert tier(cmd) is RiskTier.BLOCKED


# True key material is BLOCKED — no diagnostic value, never readable even with approval.
@pytest.mark.parametrize("cmd", [
    "cat /etc/shadow",
    "sudo cat /etc/shadow",
    "cat ~/.ssh/id_rsa",
    "cat /etc/ssh/ssh_host_rsa_key",
    "head -5 /home/azureuser/server.pem",
    "cat /opt/app/tls.key",
])
def test_key_material_reads_blocked(cmd):
    """Commands that reference private-key / shadow material should be BLOCKED."""

    assert tier(cmd) is RiskTier.BLOCKED


# A sensitive *config* (.env) is GATED, not BLOCKED: it can run with technician approval, and its
# output is redacted — so the agent can confirm e.g. a port without auto-exposing secrets.
@pytest.mark.parametrize("cmd", [
    "cat /opt/app/.env",
    "grep PASSWORD /srv/app/.env",
    "cat /etc/customer-status.env",
])
def test_sensitive_config_reads_are_gated(cmd):
    assert tier(cmd) is RiskTier.GATED


def test_sudo_prefix_does_not_bypass_block():
    """Adding sudo should not hide a dangerous command."""

    assert check_command("sudo rm -rf /").tier is RiskTier.BLOCKED


def test_targeted_chown_on_upload_dir_is_gated_not_blocked():
    """Targeted ownership fixes are allowed behind the approval gate."""

    # The rubric's explicit example: a targeted chown on an upload dir is fine.
    assert check_command("chown -R www-data:www-data /var/www/portal/uploads").tier is RiskTier.GATED


def test_compound_readonly_with_quoted_operators_is_safe():
    """Quoted shell operators should not confuse the safety splitter."""

    # A real nano-produced diagnostic: pipes/|| live inside the awk program (quoted),
    # so a quote-aware splitter must keep it read-only, not mis-classify it as GATED.
    cmd = ("sudo ss -tulpn | awk 'NR==1||/:8080/{print}' ; "
           "sudo systemctl is-enabled --quiet nginx && echo ok")
    assert check_command(cmd).tier is RiskTier.SAFE


def test_quoted_operator_does_not_hide_a_blocked_command():
    """A blocked command outside quotes must still be detected."""

    # The real rm -rf / is outside quotes and must still be caught.
    assert check_command("echo 'a | b' ; rm -rf /").tier is RiskTier.BLOCKED


def test_empty_command_blocked():
    """Empty commands are not useful and should not run."""

    assert check_command("   ").tier is RiskTier.BLOCKED


def test_allowed_convenience_flag():
    """The allowed flag should mean anything except BLOCKED."""

    assert check_command("uname -a").allowed is True
    assert check_command("rm -rf /").allowed is False


def test_systemctl_listing_with_leading_options_is_safe():
    # `systemctl --type=service --state=running,failed` is an implied list-units (read-only);
    # leading options must not be mistaken for a state-changing subcommand (regression: ticket 7005).
    assert check_command("systemctl --type=service --state=running,failed --no-pager").tier is RiskTier.SAFE
    assert check_command("systemctl --failed").tier is RiskTier.SAFE
    assert check_command("systemctl --no-pager status nginx").tier is RiskTier.SAFE


def test_systemctl_state_change_is_still_gated():
    assert check_command("systemctl enable --now nginx").tier is RiskTier.GATED
    assert check_command("systemctl restart nginx").tier is RiskTier.GATED
    assert check_command("systemctl daemon-reload").tier is RiskTier.GATED


def test_placeholder_command_is_blocked():
    # The model sometimes writes a placeholder expecting to fill it from a prior step;
    # plan steps run verbatim, so this would corrupt the file — refuse it (regression: 7005).
    heredoc = ("sudo tee /etc/systemd/system/metrics-ingest.service <<'EOF'\n"
               "ExecStart=/ACTUAL/PATH/FOUND/IN/PREVIOUS/STEP\nEOF")
    assert check_command(heredoc).tier is RiskTier.BLOCKED
    assert check_command("sudo sed -i 's|x|<dbname>|' /opt/app.conf").tier is RiskTier.BLOCKED
    assert check_command("sudo cp file /path/to/dest").tier is RiskTier.BLOCKED


def test_real_paths_are_not_flagged_as_placeholders():
    # Concrete, real-looking commands must NOT trip the placeholder guard.
    assert check_command("systemctl status metrics-ingest.service").tier is RiskTier.SAFE
    assert check_command("sudo systemctl enable --now metrics-ingest.service").tier is RiskTier.GATED
    assert check_command("sudo sed -i 's/127.0.0.1/0.0.0.0/' /opt/metrics-ingest/app.py").tier is RiskTier.GATED
