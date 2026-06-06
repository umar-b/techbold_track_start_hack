# ADR-0008: SSE for events, REST for actions, in-memory run state

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

A single technician drives one live Run at a time. We need live progress, technician actions
(approve / reject / edit / abort), and an audit trail — without production-grade resilience
engineering in a time-boxed build.

## Decision

Stream agent events to the browser over **SSE** (auto-reconnecting `EventSource`); take technician
actions as plain **REST POSTs** (`/api/runs/{id}/approve`, etc.); hold Run control state in an
**in-memory store** keyed by `run_id`; the agent loop awaits an `asyncio.Event`/`Future` set by the
approve handler, decoupled from the transport. Persist the **audit log to a per-run file**.

## Alternatives Considered

### Alternative 1: Bidirectional WebSocket + disk-persisted sessions
- **Pros**: resilient across backend restarts; one socket.
- **Cons**: session serialization at every phase boundary, reconnect rehydration, socket lifecycle — all unscored resilience engineering.
- **Why not**: over-built for a one-technician live demo.

### Alternative 2: REST polling only (no streaming)
- **Pros**: simplest.
- **Cons**: no live progress while SAFE reads auto-run after plan approval.
- **Why not**: the auto-run model needs server push; SSE is the cheap way to get it.

## Consequences

### Positive
- Reconnection "just works" (EventSource + GET current state); no session-serialization code; the only architecturally-important piece — the loop decoupled from the socket — is kept.
- Audit-to-file survives restart and feeds the activity draft (C).

### Negative
- Run control state is lost if the backend restarts mid-run (acceptable for the demo).

### Risks
- SSE proxy buffering. Mitigation: standard no-buffer headers; fall back to short polling if needed.
