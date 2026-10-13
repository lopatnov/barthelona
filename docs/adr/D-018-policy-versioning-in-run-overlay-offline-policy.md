# D-018: Policy versioning, in-run overlay, offline Policy Lab, non-patchable invariants

- Status: Proposed
- Date: 2026-10-13

## Decision

Policy versions:
- policies/vN (templates, prompts, rules, knobs, caps, MANIFEST) are immutable once released.
- Runs pin a version, and the active version is a pointer.

What the retro may change:
- In-run: overlay knobs within declared ranges, logged and revertible.
- Policy patches (JSON Patch): only through the Lab A/B on holdout (at least 3 repeats), then human G6.

Invariants no patch may touch:
- DoD, tamper and minimality dominance
- protected paths
- sandbox
- caps
- gates G1/G2/G4/G5
- hidden tests
- LLM-free gates

## Rationale

This implements the draft's self-evolving Sprint Assembly Policy reproducibly. Workflow search needs a benchmark, and in-run self-modification makes results unreproducible and invites cheating.

## Alternatives considered

- Retro writes the global policy file in-run (draft): rejected.
- No self-improvement: violates user intent.
