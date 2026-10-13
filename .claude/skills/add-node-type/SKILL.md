---
name: add-node-type
description: Checklist for adding a node type (a ready-made building block the AI can compose into sprint graphs) to the topology registry without breaking validator invariants T1-T10.
disable-model-invocation: true
argument-hint: "<node-type>"
---
# Add node type `$ARGUMENTS`

Read first: `docs/architecture.md` §9 (topology DSL, including §9.5 AI-composed graphs) and §10 (node registry), plus ADR D-003, D-004 and D-028.

1. **Registry entry** (`src/barthelona/nodes/registry.py`):
   - `type`, a `Params` Pydantic model, `reads`/`writes` (state keys), `write_scope` globs;
   - `outcomes` (e.g. `ok|fail`), `max_role` (det / main / planner / worker / cheap / escalation; roles reach models only through the profile chains in `config/models.yaml`), supported `dialects`;
   - `est_llm_calls`, `est_tokens`, `idempotent`, `timeout_s`, `retry` (transient I/O only).
2. **Implementation** under `src/barthelona/nodes/<group>/`:
   - async;
   - idempotent per (run, task, attempt);
   - state carries paths and hashes only;
   - emits `RunEvent`s;
   - LLM calls go through the gateway with a role, never a hard-coded model.

   A `human_gate`-like node makes NO LLM calls.
3. **Protected paths.** The node must never write `tests/**`, `contracts.yaml`, `project.yaml` or `gen/**` (only `header_gen` writes `gen/**`), or `.barthelona/policy*`. Validator rule T7 enforces this.
4. **Validator and schema.** Because the L1/L2 JSON schemas are generated from the registry, the new type becomes an enum value automatically. Confirm that T1–T10 still pass and that the worst-case budget estimate (T8) accounts for the node.
5. **Policy.** Make the type available to templates or slot allow-lists only in a NEW policy version (`policies/vN+1/`), never in a released one.
6. **Tests:**
   - Unit tests for the node.
   - A `FakeGateway`/`FakeExecutor` graph test covering its outcomes.
   - Hypothesis property tests: pipelines containing the node in legal positions validate; illegal placements are rejected (e.g. after `exit_ok`, writing protected paths, inside an unbounded cycle).
7. **Docs.** Add a row to the §10 table in `docs/architecture.md`. If it changes an invariant, write an ADR (`/new-adr`).
