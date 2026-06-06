# Safety, secret-redaction and degradation are enforced in code, not by the model

**Status:** accepted

Three guarantees are implemented as deterministic code paths that do not depend on
the LLM behaving well:

1. **Command blocklist (BLOCKED tier).** A regex/rule set hard-blocks dangerous blanket
   operations *before* a command can run, regardless of approval — e.g. recursive delete
   of system roots, `chmod -R 777` / recursive `chown` on top-level system dirs, database
   drops/truncation, `mkfs`, raw `dd of=/dev/*`, disabling firewall/audit/SSH, clearing
   shell history, fork bombs. A separate *warn* tier flags risky-but-legitimate commands
   (narrow `rm`/`chmod`/`chown`, installs, restarts) — allowed, surfaced, and audited.
   Blocking fires only on **blanket** system-path operations; targeted ops on a narrow
   path (e.g. a `chown` on one upload dir) are allowed.

2. **Secret redaction.** A single redactor scrubs private keys, `password=`/`token=`/
   `api_key=` assignments, and `Authorization: Bearer` headers. It runs on every stored
   command output, every audit entry, and **every Activity and Memory note field** before
   it is persisted or returned. Reading known secret paths (`/etc/shadow`, `*.env`, key
   files) is additionally BLOCKED at the command layer — defence in depth: block the read
   *and* redact any output that slips through.

3. **Graceful degradation.** If the LLM is unavailable or misbehaves, the agent falls back
   to a deterministic read-only diagnostic baseline so the end-to-end loop still runs. The
   LLM never being able to break the loop is a hard requirement, not a nicety.

## Why

- Directly serves the C block (no dangerous blanket commands, secret protection, complete
  audit) and the E block (error handling, robustness, tests).
- Safety that depends on the model "choosing" to be safe is not safety. The model proposes;
  code disposes (see ADR-0002).
- A small/optional model (`gpt-5.4-nano`) and flaky external services must never take the
  workflow down during a live demo or grading run.

## Consequences

- The blocklist, redactor, and fallback are unit-tested (mocked, no network) — part of the
  E "tests present and runnable" requirement.
- Modules stay single-responsibility (ERP client / SSH runner / safety / audit+redaction /
  agent / activity generator / memory) so each guarantee lives in one auditable place.
