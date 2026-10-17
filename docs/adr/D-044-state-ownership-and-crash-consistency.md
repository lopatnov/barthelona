# D-044: State ownership and crash consistency

- Status: Proposed
- Date: 2026-10-17
- Amends: D-002, D-003, D-024

## Context

A run's state lives in four places: the LangGraph checkpoint (`var/checkpoints.sqlite`), `app.sqlite` (events, gates, commands, ledger), the workspace git repository with `.barthelona/`, and files under `var/runs/<id>/`. Architecture §7 promises that resume does not re-run finished nodes, and §17 batches events about every 250 ms, but no text says which store wins when a crash falls between a side effect, its event and its checkpoint (issue #64). Evidence in the code:

- `Store.append_events` takes caller-assigned, strictly contiguous `seq`. A node replayed after a crash either raises `ConflictError` or logs the same fact twice.
- A node that calls an LLM is not idempotent: a replay pays again and gets a different answer.
- Only the topology has a `builder_version`. The LangGraph state shape and node semantics are unversioned, but a run waiting at a gate can outlive a code upgrade.

## Decision

1. **Ownership.**
   - The workspace git repository and `.barthelona/` own project artifacts and plans (code, contracts, tests, backlog, topology, increments).
   - `app.sqlite` owns the operator-visible record: runs, events, gates, commands, the cost ledger.
   - The LangGraph checkpoint owns only the control position (which node is next) and holds paths and hashes, never content (as §7 already says).
   - `var/runs/<id>/llm/` owns recorded model responses.
2. **Write order in a side-effecting node:** (a) the effect, idempotent and keyed by run, task, attempt and node (a commit checks that its tag exists; `apply_patch` checks the content hash); (b) its events, each with a `dedupe_key`, unique per run, so a replayed append is a no-op and the store assigns `seq`; (c) the checkpoint. A crash between (a) and (c) re-runs the node and every step becomes a no-op.
3. **LLM calls are reused, not repeated.** On resume the gateway looks up the recorded response for the same (node, attempt, prompt hash) before calling a provider. The ledger is idempotent by call key. This is the cassette mechanism of §19 used for recovery.
4. **Events that define resumable truth** (`gate_requested`, `increment`, `stop`) are flushed synchronously before the checkpoint. Other events keep the 250 ms batch.
5. **Run compatibility.** `Run.engine_state_version` (an integer, bumped when the graph state schema or a node's semantics change incompatibly). The worker resumes only supported versions. Otherwise it stops the run with `infra_error`, logs `run_incompatible`, and offers a new run that starts from the last `inc-NN` tag; backlog, contracts and tests are files in the workspace, so nothing is lost at sprint granularity.
6. **The crash spike** (Phase 1 exit) kills the worker at each seam: after the effect, after the event, mid-batch, during a gate. It asserts no duplicate event, commit, tag or paid call.

## Rationale

Splitting ownership by what each store is good at avoids a single store that the UI could not read (invariant 8: the UI never imports LangGraph) and a workspace that would no longer build without barthelona. Idempotent effects plus dedupe keys are cheaper and easier to test than a two-phase commit across SQLite files and git. Reusing recorded LLM responses turns the most expensive non-idempotent step into a lookup.

## Alternatives considered

- **Everything in the LangGraph checkpointer.** The UI would need LangGraph, and workspace artifacts would live outside git.
- **Event sourcing with full replay.** Rebuilds state from events; heavy for this project, and events are capped at 16 KiB payloads by design.
- **Two-phase commit across stores.** Overkill for a single-user local tool.
- **Never support resume across upgrades; always restart.** Loses days of paused runs for every code change; the version check is cheaper.

## Consequences

- `RunEvent.dedupe_key`, a unique index in the next migration, and a store-assigned `seq`; `Run.engine_state_version` (issue #64).
- `docs/architecture.md` §7, §17 and §18 are updated in the same change; the roadmap Phase 1 spike text names the crash points.
- Relates to issues #10 (status transitions) and #12 (duplicate resume), which become simple cases of the same rules.
