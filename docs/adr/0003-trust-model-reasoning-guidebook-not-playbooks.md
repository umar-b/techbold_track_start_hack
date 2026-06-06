# Trust the model to reason; guidebook is method + knowledge, not playbooks

**Status:** accepted

The agent diagnoses by **reasoning over live evidence**, not by matching against
hard-coded per-incident fix recipes. The Guidebook gives it (a) a diagnostic *method*
(gather evidence → ranked hypotheses with evidence → test cheapest first → minimal fix →
verify) and (b) reference knowledge about common Linux failure classes — as facts it may
draw on, not as forced decision branches.

## Why

- The B block is graded on **fresh, unseen incidents**, "rewarding generalisation over
  hard-coding." Rigid playbooks only help on incidents we anticipated and look like the
  hard-coding the grader is built to defeat. Free reasoning generalises to the unexpected.
- It is model-agnostic: swapping the current small model (`gpt-5.4-nano`) for a stronger
  one later strictly improves results with no rewrite. Playbooks would have to be
  re-tuned.

## The hard limits that are NOT left to reasoning

Two things stay enforced in code as invariants regardless of how the model reasons, because
they are guarantees, not judgments:

- **Safety** — the SAFE/GATED/BLOCKED tiers and approval gates (see ADR-0002).
- **Persistence** — every fix is verified to survive a reboot (`is-enabled` / on-disk /
  survives-restart), since a fragile fix caps the B "fix persists" point.

So: the model reasons about *what is wrong and how to fix it*; code enforces *what is safe
and what counts as done*.

## Trade-off accepted

A small model reasoning freely can mis-diagnose. Mitigated by the structured
hypothesis-with-evidence format, tight context (trim noisy command output before it
re-enters the prompt), and memory that pre-fills plans as hypotheses-to-verify — never
as actions-to-apply (see ADR-0001). The bet is that this beats brittle recipes on unseen
incidents and ages better as models improve.
