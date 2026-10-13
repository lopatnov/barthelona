# D-017: Lessons are evidence-gated memory

- Status: Proposed
- Date: 2026-10-13

## Decision

Lessons are created only from evidence where a failure turned into a pass (with the diff attached), and are keyed by scope and normalized error_sig.

Lifecycle:
- candidate → active, when its regression check passes;
- active → approved, by a human in the inbox;
- deprecated, when the toolchain changes or confidence drops below 0.35.

Exact error_sig lookup comes before similarity.

Score = alpha/(alpha+beta) × decay, updated only from cited uses.

SQLite is the source of truth; Qdrant only indexes lessons.

## Rationale

Reflexion gains depend on external feedback.

Lessons without evidence pollute the context, and rejected lessons kept as negative memory prevent loops.

The benchmark gates whether lessons are injected at all.

## Alternatives considered

- Draft: every reflection goes straight to Qdrant and into the coder prompt. Unvalidated, so drift and poisoning.
