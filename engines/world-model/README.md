# World Model (TypeScript)

`index.ts` is an event-sourced shared state for agents that run in parallel: entities, contexts, relationships and
facts with provenance, graph queries, historical snapshots and an audit trail. It follows the Meterless World Model
spec (`engines/world-model/AGENTS.md` in https://github.com/Meterless/Meterless) and was written for the
hackathon's Meterless track.

## Status

- **Used as the shared-state reference.** The pipeline records run facts through the Python store
  `src/barthelona/world_model/` (D-058); this file stays the conformance reference. The slow integration test
  `tests/unit/world_model/test_ts_bridge.py` drives it through `bridge/cli.ts` when `npx tsx` exists, and checks
  the two implementations derive the same stable IDs and both report an empty diff on re-ingest.
- **Conformance is not shown yet.** The Meterless runner is not in this repository. To check it, clone the Meterless
  repository somewhere outside this one (the repo rule is never to run code from `.reference/`) and run, from its
  checkout:

  ```
  WORLD_MODEL_IMPL=/absolute/path/to/engines/world-model/index.ts npx tsx conformance/runner.ts
  ```

  Until that passes, treat the implementation as unverified.

- **Concurrent writers are not tested.** The class has no locking, and this repository has no test with several
  writers; writers in separate processes, or on the file store, are not covered.

## Run

The file imports only `node:fs` and `node:path` and exports `WorldModelClass`. There is no build step; `tsx` runs it
directly.
