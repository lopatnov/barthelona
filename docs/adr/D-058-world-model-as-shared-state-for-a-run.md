# D-058: World Model as shared state for a run

- Status: Proposed
- Date: 2026-10-25
- Amends: D-045

## Context

The World Model (`engines/world-model/`, TypeScript, the Meterless spec) is built and passes its own
conformance tests, but nothing in the pipeline uses it yet: `docs/zetaris-engines.md` still lists the row
"World Model (shared state)" as `next`. Issue #297 asks for the first slice: a run records its facts in the
World Model, so parallel or later drafts plan from the same state, and Live Run can show it.

Prior art: [`engines/world-model/README.md`](../../engines/world-model/README.md),
[`docs/meterless-prompts/README.md`](../meterless-prompts/README.md) rows 13, 18, 22-24, and
[`src/barthelona/llm/hmem.py`](../../src/barthelona/llm/hmem.py) (the H-MEM port, which already follows the same
Meterless conventions). The TypeScript reference is at
<https://github.com/Meterless/Meterless/tree/main/engines/world-model>.

## Decision

1. A new Python package `src/barthelona/world_model/` is the product's shared-state store. It is a folded
   snapshot of entities, optionally persisted as one JSON file (`var/world-model/barthelona.json` by default),
   with no Node dependency. The TypeScript implementation remains the conformance reference.
2. A run records four entity kinds with stable external keys: `run` (`{run_id}`), `requirement`
   (`{run_id}:requirement:{id}`), `test` (`{run_id}:test:{id}`) and `attempt` (`{run_id}:attempt:{index}`).
   Stable IDs are `ext_<hash>` derived from the key by the same djb2 hash the TypeScript `externalId` uses, so
   re-ingesting a run gives an empty diff.
3. The worker writes as the run goes: the run, requirement and test entities after `validate_spec` accepts the
   spec; an attempt entity after the oracles judge each attempt; the stop reason onto the run entity when the
   run stops. Every write carries provenance — which model answered (`last_call`) and which route (role) asked.
4. The code step recalls the relevant entities before each attempt (the prior runs of the same spec slug),
   next to the Zetaris facts and the H-MEM recall, marked as untrusted data.
5. `python -m barthelona runs world <run_id>` and a Live Run panel list a run's entities from the same file the
   worker writes; SQLite remains the UI/engine boundary (invariant 8).
6. Unit tests use an in-memory World Model (no Node). One integration test, marked `slow`, drives the real
   TypeScript implementation through `npx tsx` and skips when Node is unavailable.
7. Layering (D-045): `ui` and `engine` may import `world_model`; `world_model` imports only `domain` and the
   standard library — never the engine, LangGraph or Streamlit.

## Rationale

- No Node in production: the worker stays a pure Python process, and the World Model is optional like Zetaris
  (a write that cannot persist never stops the run).
- Stable, key-derived IDs are what makes re-ingest idempotent, which is the Meterless "ingest once, never
  twice" guarantee, and they let the slow test prove the Python and TypeScript stores agree.
- A single file-backed store lets the worker, the CLI and the UI read the same state without the UI importing
  the engine.
- Provenance (model + route) keeps the trust ledger queryable, matching H-MEM's source convention.

## Alternatives considered

- **Drive the TypeScript implementation directly from the worker** (one Node process per write). Rejected:
  adds a hard Node runtime dependency and a subprocess per event for the common path; the TS reference is
  reached only by the slow conformance test.
- **Port the TypeScript event log verbatim** (append JSONL and fold on load). Rejected for now: more code for
  no benefit while the sprint loop that would need several concurrent writers does not exist yet. The folded
  snapshot is the honest single-process slice; the TS event log stays the conformance target.
- **Store World Model state in `var/app.sqlite`** through `persistence`. Rejected: SQLite is the invariant-8
  boundary between the UI and the engine, not the shared-state store; the World Model keeps its own file, which
  the UI may read directly.

## Consequences

- A new `var/world-model/` file is written by the worker; the CLI and the UI read it. It is runtime data and
  stays gitignored with `var/`.
- The engines table in `docs/architecture.md` §3.1 and `docs/zetaris-engines.md` move the World Model row from
  "next" to working.
- `tests/unit/test_layering.py` adds `world_model` to the UI's allowed packages, amending D-045's table.
- The `slow` integration test is excluded from the default `pytest` marker selection, so CI stays green without
  Node.
