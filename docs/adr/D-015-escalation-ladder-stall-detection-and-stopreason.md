# D-015: Escalation ladder, stall detection and StopReason

- Status: Proposed
- Date: 2026-10-13
- Amended by: D-030

## Decision

Per-task escalation:
- E0: retry with structured diagnostics
- E1: deterministic context enrichment (facts, lessons by error_sig, filtered docs, callee code)
- E2: candidates (N=2–3 locally, ranked by the oracle)
- E3: cloud model, only if cloud_allowed
- E4: human via G5

The same error_sig twice, or a repeated patch hash, jumps to the next rung.

Every stop records a StopReason enum value.

## Rationale

A few diverse attempts beat long repair chains, and sampling pays only with an automatic checker.

Stall detection stops wasting minutes at about 8 tok/s.

Explicit stop reasons make runs debuggable and give the benchmark something to measure.

## Alternatives considered

- Web search after 3 failures (draft): prompt-injection surface; deferred to P5 and gated.
- Unbounded retries: never.
