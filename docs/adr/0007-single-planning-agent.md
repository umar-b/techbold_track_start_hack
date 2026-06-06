# ADR-0007: Single planning agent with a tool belt, not a multi-agent pipeline

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

The brief allows either a single planning agent with tools or several specialised agents
(`problem_analyzer`, `customer_system_analyzer`, `problem_solver`, `activity_log_generator`). The
rubric scores outcomes, not agent count, the build is time-boxed, and a human approval gate must
thread through the whole loop.

## Decision

Use one planning agent with a tool belt (SSH runner, ERP client, and so on). The "specialised
agents" become labelled stages/prompts within that single loop: analyse → plan → execute → verify
→ document.

## Alternatives Considered

### Alternative 1: Multi-agent pipeline
- **Pros**: clean separation on paper; a pitchable narrative.
- **Cons**: inter-agent handoff plumbing, more failure surface, and a harder time threading one approval gate through four actors.
- **Why not**: cost with no score attached; the staged single agent presents the same story in the demo.

## Consequences

### Positive
- One control loop, one place the approval gate lives, one context to manage.

### Negative
- Less physical separation of concerns than discrete agents.

### Risks
- One loop's context bloats over a long run. Mitigation: trim/summarise command output before it re-enters the prompt.
