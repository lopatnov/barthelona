# D-004: Closed topology grammar: templates + slots + knobs, checked by validator rules T1–T10

- Status: Proposed
- Date: 2026-10-13
- Amended by: D-028

## Decision

The template catalogue is delivered across immutable policy versions (v1 in Phase 1: module_create, symbol_patch, fix_build, a minimal contract_change, integration; v2 in Phase 2 adds candidates and the trace_capture slot). Amended by D-028: L1/L2 composition. Target catalogue:
- module_create, symbol_patch, fix_build, candidates, contract_change, and the sprint-level integration template.

Slots (pre_code, post_apply, on_fail) accept only listed optional node types.

Knobs have types, ranges and caps.

The TopologyRequest schema is generated from the active policy as enums.

The validator (built on networkx) enforces:
- vocabulary and identity;
- structure and totality;
- exactly one declared back-edge per strongly connected component, with max_iters ≤ cap;
- DoD, tamper and minimality dominance;
- write scopes;
- a worst-case LLM-call budget;
- tier and consent;
- gate hygiene.

## Rationale

This gives the planner real choices (insert a macro_expand_check, raise the fix iterations, use candidates) while making termination, verification and cost provable before execution.

Pydantic alone checks shape, not termination. The audit flagged this explicitly.

## Alternatives considered

- Enum-only template choice: too rigid for the Meta-Agentic Scrum concept.
- Arbitrary node/edge lists from the LLM: unverifiable in practice.
