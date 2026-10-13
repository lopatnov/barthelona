# D-009: Frozen tests and contracts; tamper and minimality gates

- Status: Proposed
- Date: 2026-10-13

## Decision

After G1/G2, tests and contracts are locked and hashed, and coding roles cannot write them.

Changing them requires a contract_change story and G2. In edit mode, changing a characterization test requires a ChangeSpec that marks it superseded.

The tamper gate:
- checks the hashes of protected files;
- requires gen/ to regenerate byte-identically;
- requires that no file outside the write scope changed.

The minimality gate (edit mode) restricts edits to the declared symbol spans.

## Rationale

This prevents an agent from "passing" by weakening tests or drifting contracts, a known failure mode once there is a self-improvement loop. Hidden benchmark tests add a second layer.

## Alternatives considered

- Trust the LLM reviewer: insufficient.
- Allow test edits with logging: too easy to game.
