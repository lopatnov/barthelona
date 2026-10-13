---
paths:
  - "src/barthelona/engine/**"
  - "src/barthelona/nodes/**"
  - "src/barthelona/policy/**"
  - "src/barthelona/domain/topology*.py"
  - "policies/**"
---
# Engine, nodes, topology and policy rules (docs/architecture.md §5–§11, ADR D-001…D-004, D-018, D-028)

- LangGraph 1.2.x:
  - Graph state holds paths, ids and hashes, never file contents.
  - Nodes are idempotent, keyed by (run, task, attempt).
  - Checkpoints use `durability="sync"`.
  - Every node has an async timeout. `RetryPolicy` is only for transient I/O.
- `interrupt()` appears only in `human_gate` nodes. Those nodes make no LLM calls and are never wrapped in a bare `try/except` (a resumed node re-runs from its first line).
- Sprint topologies (L0 rules, L1 template + slots + knobs, L2 whole pipelines) are data:
  - validated by T1–T10;
  - persisted to `.barthelona/sprints/NN/topology[.rK].json` with `spec_hash` BEFORE execution;
  - compiled by a pure function.

  Changing the validator or compiler requires the Hypothesis property tests to stay green: random graphs and mutations are rejected; every catalogue template with every legal insertion set is accepted.
- Every loop declares a `LoopBound` (`max_iters` plus optional `max_wall_s` / `max_tokens` / `max_usd`), an `on_exhaust` edge and a stall rule. Every run stop sets a `StopReason`.
- Re-planning rewrites only the remaining work, is bounded by `max_replans`, and is persisted as a new revision.
- New node types: use the `add-node-type` skill. Node types are code, never LLM-generated.
- Released `policies/vN/` (`MANIFEST.json` `"released": true`) are immutable; create vN+1. Policy invariants (DoD dominance, tamper/minimality gates, protected paths, sandbox profile, caps, gates G1/G2/G4/G5, hidden tests never in prompts) cannot be changed by overlays or patches.
- The engine never imports Streamlit. It communicates with the UI only through `var/app.sqlite`.
