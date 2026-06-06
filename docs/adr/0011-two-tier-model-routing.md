# ADR-0011: Two-tier model routing — fast model for diagnosis, reasoning model for planning

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)
**Refines**: ADR-0010 · **Revisits**: ADR-0006 (which ruled out routing when only one deployment existed)

## Context

Live testing showed `gpt-5.4-nano` diagnoses competently but does not reliably converge to a
fix — it over-diagnoses and rarely commits to a correct, persistent plan (the score bottleneck is
reasoning quality at the planning step, not infrastructure). The track later provided a second,
stronger deployment, `gpt-5.4`, on the same Azure resource and key. Verified live: `gpt-5.4`
answers on the same OpenAI-compatible `/chat/completions` path with `response_format=json_object`
— identical to the nano path — so routing costs no new code path. The stronger model is more
expensive, so it must be used sparingly.

## Decision

Route by role, not by step. **All in-loop reasoning** — deciding the next diagnostic *and*
synthesising evidence into a root cause + ordered fix — uses the **reasoning** model
(`LLM_REASONING_MODEL`, e.g. `gpt-5.4`), because deciding *what to probe* and *when to stop* is
itself the analysis where the fast model was weak (it over-probed and never converged). The
**fast** model (`LLM_MODEL` / `AZURE_OPENAI_DEPLOYMENT`, e.g. `gpt-5.4-nano`) is reserved for
non-reasoning text — the activity-log draft. `llm.complete_json(..., reasoning: bool)` selects the
tier; the agent passes `reasoning=True` for every diagnose/plan call, while activity drafting omits
it. Empty `LLM_REASONING_MODEL` disables routing (fast model everywhere). Both tiers use the same
provider/endpoint/key and the same JSON-mode path (ADR-0010).

## Alternatives Considered

### Alternative 1: One model for everything (status quo, ADR-0006)
- **Pros**: simplest; one deployment.
- **Cons**: nano under-converges on planning; gpt-5.4 everywhere burns tokens on cheap diagnosis steps.
- **Why not**: routing targets the exact bottleneck (planning) while keeping diagnosis cheap.

### Alternative 2: Reasoning model for the plan/replan step only; fast model investigates
- **Pros**: cheapest reasoning-model usage (~1 call/run); the track warned to use it sparingly.
- **Cons**: the fast model still owns *what to probe* and *when to stop* — the exact analysis it was weak at — so the plan is built on a possibly poor investigation.
- **Why not**: chosen initially, then revised — investigation quality feeds plan quality, so the reasoning model owns the whole loop. (See Consequences: token cost accepted deliberately.)

### Alternative 3: Hybrid — reasoning model decides intent, fast model writes the literal command
- **Pros**: cheap command authoring.
- **Cons**: two round-trips per step, more latency/plumbing; the reasoning model can emit the command itself, so the fast call adds little.
- **Why not**: complexity without real savings.

## Consequences

### Positive
- Stronger reasoning across the whole investigation — better probe selection, earlier convergence, fewer wasted steps — not just at the final plan.
- Zero new code path: same provider/endpoint/key/JSON-mode seam, just a different model string.
- Model-agnostic (ADR-0010) preserved — the reasoning tier works for any provider via `LLM_REASONING_MODEL`.

### Negative
- Higher token cost: the reasoning model now fires on every diagnose/plan call (~7–10/run) instead of once. Accepted deliberately for quality; the track warned to use the strong model sparingly, so revisit if quota bites.
- Two model names to configure; a misconfigured reasoning model silently falls back to the fast one.

### Risks
- `gpt-5.4` latency/quota across a full run could slow things or hit limits. Mitigation: the diagnose soft-limit caps the number of reasoning calls; existing timeouts apply; lower the soft-limit if convergence is fast enough to need fewer probes.
- Embeddings (`text-embedding-3-large`) are available on the same resource but remain **unwired** —
  memory is a markdown graph (ADR-0001) and is not on the scoring path. Config keys exist so
  semantic recall is a later config-plus-small-client change, not a rework. Revisit only if recall
  quality demands it.
