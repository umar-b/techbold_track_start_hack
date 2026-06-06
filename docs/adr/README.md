# Architecture Decision Records

Architectural decisions for the AI Service Desk Autopilot, recorded as they were made.
Format: lightweight [Nygard ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
See [`template.md`](template.md) for new entries. Domain vocabulary lives in
[`../../CONTEXT.md`](../../CONTEXT.md).

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-memory-markdown-graph-not-vector-db.md) | Memory as a sanitized markdown graph, not a vector database | accepted | 2026-06-06 |
| [0002](0002-plan-level-approval-risk-tiers.md) | Plan-level approval with SAFE / GATED / BLOCKED risk tiers | accepted | 2026-06-06 |
| [0003](0003-trust-model-reasoning-guidebook-not-playbooks.md) | Trust the model to reason; guidebook is method + knowledge | accepted | 2026-06-06 |
| [0004](0004-code-enforced-safety-redaction-and-fallback.md) | Safety, secret-redaction and degradation enforced in code | accepted | 2026-06-06 |
| [0005](0005-persistence-without-self-reboot.md) | Verify fix persistence without self-rebooting; reboot is gated | accepted | 2026-06-06 |
| [0006](0006-single-llm-provider-azure.md) | Single LLM provider (Azure OpenAI), no provider abstraction | superseded by ADR-0010 | 2026-06-06 |
| [0007](0007-single-planning-agent.md) | Single planning agent with a tool belt, not a multi-agent pipeline | accepted | 2026-06-06 |
| [0008](0008-sse-rest-in-memory-state.md) | SSE for events, REST for actions, in-memory run state | accepted | 2026-06-06 |
| [0009](0009-memory-seeds-hypotheses-not-actions.md) | Memory seeds plans as hypotheses-to-verify, never actions | accepted | 2026-06-06 |
| [0010](0010-langchain-agent-framework-model-agnostic.md) | Adopt LangChain as the agent framework (model-agnostic), replacing the custom loop | accepted | 2026-06-06 |
