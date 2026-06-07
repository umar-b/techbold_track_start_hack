# Linux troubleshooting guidebook

Method, not recipes (ADR-0003). Use this to reason; do not blindly apply steps.

## Diagnostic method
1. Gather read-only evidence (service state, logs, ports, disk, config).
2. Rank hypotheses with the evidence for each — pick the cheapest to test first.
3. Apply the **smallest** change that fixes the **root cause**, not the symptom.
4. Validate: re-check the symptom with read-only checks. The provided test
   `sudo /opt/hackathon/public-test.sh` is GATED — include it in the plan's validation (it runs
   after the technician approves), never as a standalone diagnostic.
5. Confirm persistence (see below).

## Persistence (graded — ADR-0005)
A fix must survive a reboot. Rebooting these VMs **redeploys them to the broken state**, so
never reboot to "test"; verify persistence cheaply instead:
- Service should be **enabled**, not just started: `systemctl enable --now <svc>`; check `systemctl is-enabled`.
- Mounts belong in `/etc/fstab`; firewall rules must be persisted; config changes written to disk.
- Fix the *generator* of a recurring problem (e.g. logrotate), not just its current effect.

## Common failure classes (knowledge, not branches)
These are illustrative examples of the METHOD, not an exhaustive checklist and not tied to any
specific ticket. The incident in front of you may be a different class entirely — apply the same
loop (live evidence → name the specific broken component → smallest persistent fix → validate) to
whatever the system actually shows. Let the evidence pick the class; do not force the symptom into
one of these.
- **Service down / not enabled** — `systemctl status/is-enabled`, `journalctl -u <svc>`. Fix the
  cause (bad config, dependency), then `enable --now`.
- **Permissions** — upload/data dir not writable by the app user. Use a **targeted** `chown`/`chmod`
  on that path (least privilege — prefer correct ownership over `777`). Never recurse over system roots.
- **DNS / network** — host unresolved or blocked. Check `getent hosts <name>`, `/etc/hosts`,
  `ss -tlnp`, firewall. Persist `/etc/hosts` or firewall rules on disk.
- **Disk full** — `df -h`, `du`. Free space safely (rotate/remove *safe* temp); fix the generator.
  Postgres can go read-only when the disk is full (reads work, writes fail).
- **DB write fails / grants** — read works, insert fails. Check disk first, then the role's
  privileges. `GRANT` the missing privilege to the app role — **do not** reinit the DB or run the
  app as a DB superuser to bypass permissions (hard fail).
- **Stopped collector / cron** — data not updating though the app is up. Find the feeder
  service/cron, restart **and enable** it; check timestamps.

## Safety (code-enforced anyway — ADR-0002/0004)
Never: blanket `chmod -R 777` / recursive `chown` / `rm -rf` on system roots; drop/reinit a
database; delete customer data; disable firewall/audit/SSH; read or expose secrets; delete logs
to hide actions. Targeted operations on a narrow application path are fine.
