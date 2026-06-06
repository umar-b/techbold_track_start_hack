# ADR-0005: Verify fix persistence without self-rebooting; reboot is a gated action

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

The B grader awards a point per incident for "the fix persists after a reboot or relevant
service restart," and the reset endpoint reboots the VMs. A green-now-only fix (e.g.
`systemctl start` without `enable`) caps the fix score and fails the persistence check. We must
guarantee persistent fixes without destabilising the Run.

## Decision

The agent prefers persistent mechanisms (enable services, write to `fstab`/config-on-disk,
persist firewall rules, fix the root generator rather than the symptom). The verifier asserts
persistence cheaply — `systemctl is-enabled`, config-on-disk, optional service restart — **without
rebooting**. An actual reboot is a GATED, explicitly-confirmed high-risk action: on approval the
Run issues the reboot, polls-reconnects with backoff until the VM answers, then re-verifies.

## Alternatives Considered

### Alternative 1: Self-reboot in the verifier to prove persistence
- **Pros**: certainty the fix survives a reboot.
- **Cons**: slow; drops SSH mid-run; pulls reconnect logic onto the critical path; the grader reboots anyway.
- **Why not**: cost outweighs benefit — `is-enabled`/on-disk checks give the signal cheaply.

### Alternative 2: Only validate "symptom gone" (no persistence check)
- **Pros**: simplest.
- **Cons**: green-now-only fixes silently lose the persistence point across incidents.
- **Why not**: leaves B points on the table.

## Consequences

### Positive
- Fixes survive the grader's reboot by construction; no mid-run reboot instability on the common path.

### Negative
- `is-enabled`/on-disk checks are a proxy, not a real reboot.

### Risks
- A fix that passes the check but not reality. Mitigation: prefer the canonical persistent
  mechanism, optional service restart, and rehearse with the reset endpoint during development.
