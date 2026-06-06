# ADR-0001: Memory as a sanitized markdown graph, not a vector database

**Date**: 2026-06-06
**Status**: accepted
**Deciders**: Team (umar-b + teammates)

## Context

The product's differentiator is an "it learns from past incidents" memory. The 35-point
troubleshooting block is graded on **fresh, unseen VMs**, explicitly to reward generalisation
over hard-coding, so semantic recall of a *similar past fix* only pays off when the same
incident recurs — which the grader avoids by design. We need a memory that is cheap, demo-able,
and carries no infrastructure or demo-time risk.

## Decision

Store resolved incidents as linked markdown notes (one per incident, Obsidian-style
`[[wiki-links]]`), retrieved by a lexical tag/keyword prefilter plus one-hop graph traversal.
No embeddings, no vector database. Storage location is configurable (`MEMORY_DIR`): a committed
directory for the hackathon, an external file server in production.

## Alternatives Considered

### Alternative 1: ChromaDB + sentence-transformers embeddings
- **Pros**: semantic similarity matches differently-phrased symptoms; the "obvious" AI-memory approach.
- **Cons**: ~80 MB model download at first run (a demo-time failure point); infra + build cost.
- **Why not**: earns ~0 score because grading is on fresh VMs, while adding real cost and fragility.

### Alternative 2: Flat list / single JSON log
- **Pros**: trivial to build.
- **Cons**: no relationships between incidents; cannot surface related fixes.
- **Why not**: loses the "connected brain" value that makes the feature compelling.

## Consequences

### Positive
- No infra and no model download; works at small scale.
- Graph links surface related incidents a flat search would miss.
- Pluggable storage location — same code for hackathon and production.

### Negative
- Lexical retrieval can miss differently-phrased symptoms a vector search might catch.

### Risks
- Notes are committed to a public, secret-scanned repo, so a leaked secret is a hard fail.
  Mitigation: every note passes the secret redactor (ADR-0004) and stores command classes /
  redacted forms, never raw secret-bearing output; notes are append-mostly to avoid
  re-introducing unsanitised content. Seeding behaviour is specified in ADR-0009.
