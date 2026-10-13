# D-003: Sprint topologies are persisted data compiled deterministically, with an interpreter fallback

- Status: Proposed
- Date: 2026-10-13

## Decision

Lifecycle of a sprint topology:
1. Validate the SprintTopology.
2. Persist it with spec_hash and builder_version before execution.
3. Compile it with a pure function into a subgraph.
4. Invoke it from the fixed outer run_sprint node.
5. On resume, rebuild it from the persisted JSON.

A Phase 1 spike must prove crash/resume and gate/resume without re-running finished nodes. If the spike fails, switch to an interpreter subgraph that walks the same data with a cursor in state.

## Rationale

LangGraph builds graphs at runtime, but checkpoints are keyed by node names. MS Agent Framework documents the same rule: a rehydrated workflow must preserve its topology.

Deterministic rebuilding from persisted data satisfies this. The interpreter fallback keeps the node registry, the validator and the templates unchanged, so the risk is contained.

## Alternatives considered

- Build and destroy graphs from live LLM JSON (draft): fragile resume.
- Always use the interpreter: simpler, but loses native per-node policies and visualization. Kept as the fallback.
- A fixed graph only: loses meta-agency.
