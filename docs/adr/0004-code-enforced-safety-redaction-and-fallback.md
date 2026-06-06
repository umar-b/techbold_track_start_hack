# ADR-0004: Safety, secret-redaction and degradation enforced in code

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

The C block requires no dangerous blanket commands, secret protection, and a complete audit
trail; the E block requires robustness and tests. Safety that relies on the model choosing to
behave is not safety, and a small/optional model plus flaky external services must never take a
live demo or grading run down.

## Decision

Three guarantees are deterministic code paths, independent of model behaviour:
1. **Command blocklist (BLOCKED tier)** + a *warn* tier, checked before any command runs —
   hard-blocking blanket deletes/`chmod -R 777`/recursive `chown` on system roots, DB
   drops/truncation, `mkfs`, raw `dd of=/dev/*`, disabling firewall/audit/SSH, clearing history,
   fork bombs; warning on narrow risky ops (allowed, surfaced, audited).
2. **Secret redaction** applied to all command output, audit entries, and every Activity and
   Memory field, plus **BLOCKING reads** of known secret paths (`/etc/shadow`, `*.env`, key files).
3. **Graceful degradation** — a read-only diagnostic fallback so the loop runs when the LLM is
   unavailable.

## Alternatives Considered

### Alternative 1: Rely on the model / system prompt for safety
- **Pros**: no code.
- **Cons**: non-deterministic; one bad generation is a hard fail.
- **Why not**: safety must not depend on model behaviour.

### Alternative 2: Redaction only (no secret-read block)
- **Pros**: simpler.
- **Cons**: reading a secret then redacting it still *reads* it — a hard-fail category.
- **Why not**: block the read **and** redact the output — defence in depth.

## Consequences

### Positive
- Directly serves C (safety, audit) and E (robustness, tests); each guarantee lives in one auditable module.

### Negative
- Regex blocklists can over- or under-match and need test coverage and tuning.

### Risks
- A novel dangerous command slips the blocklist. Mitigation: conservative patterns scoped to
  blanket system-path operations, the warn tier, and human plan approval as a backstop.
