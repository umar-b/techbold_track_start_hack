# Memory is a sanitized markdown graph, not a vector DB

**Status:** accepted

The product's "it learns from past incidents" memory is stored as linked markdown
notes (one per resolved Incident, Obsidian-style `[[wiki-links]]`), retrieved by a
lexical tag/keyword prefilter plus one-hop graph traversal — **no embeddings, no vector
database.**

## Why

- The 35-point troubleshooting block (B) is graded on **fresh, unseen VMs**, explicitly
  to "reward generalisation over hard-coding." Semantic recall of a *similar past fix*
  only pays off when the same incident recurs — which the grader avoids by design. So a
  vector store (ChromaDB + sentence-transformers) earns ~0 score while costing real build
  time and a model download at demo time.
- What actually generalises to fresh incidents is general Linux knowledge (in the
  Guidebook + system prompt), not stored past cases.
- At this scale (a handful of notes) lexical match + link traversal is sufficient, has no
  infra, and makes the graph structure do visible work (links surface related incidents a
  flat search would miss).

## Considered and rejected

ChromaDB + `all-MiniLM-L6-v2` embeddings (the original design). Rejected: no score impact
on fresh-VM grading, plus an 80 MB model download as a demo-time failure point.

## Consequences

- Notes are committed to the repo (shared "brain") **behind a hard sanitizer** — they are
  public + secret-scanned, and committing a secret is a hard fail. Notes store command
  *classes / redacted forms*, never raw secret-bearing output.
- Storage location is configurable (`MEMORY_DIR` / storage backend): committed dir for the
  hackathon, an external file server in production — same code.
