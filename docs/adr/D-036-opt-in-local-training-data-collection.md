# D-036: Opt-in, local collection of training data from code-producing attempts

- Status: Proposed
- Date: 2026-10-14
- Amends: none (D-025 keeps fine-tuning itself deferred; this decides only how the data is gathered)

## Context
The owner wants barthelona to gather data for training a model that programs in assembly (2026-10-14). Every run produces exactly that material: prompts assembled from contracts and facts, the patch envelopes the models answer with, and the oracles' verdict on each attempt (assembler and linker errors, ABI findings, test results), including failed attempts followed by fixes. Today the per-call LLM files under `var/runs/<id>/llm/` are written for replay (D-024); they are keyed by run, mix every role and carry no oracle verdict, so they are not a usable dataset.

Prior art:
- SWE-Gym (https://arxiv.org/abs/2412.21139): agent trajectories kept as training data only when the tests pass (rejection-sampling fine-tuning).
- STaR (https://arxiv.org/abs/2203.14465): self-generated rationales filtered by answer correctness.
- DPO (https://arxiv.org/abs/2305.18290): preference pairs (rejected, chosen) train without a reward model; a failed attempt followed by an accepted fix of the same task is such a pair.
- In this repo, lessons (D-017) already pair a failure with the fix that turned it green, but keep only a rule, not the attempt texts.

## Decision
1. **Setting, off by default.** `BARTHELONA_TRAINING_DATA_ENABLED` (default off) and `BARTHELONA_TRAINING_DATA_DIRECTORY` (default `var/training`), read by `TrainingDataSettings` from the process environment only, never from `.env`. `barthelona training status` shows the setting and the sample counts. From Phase 1 the New request page offers a "Collect training data" checkbox that defaults to the setting; the choice is pinned on the run as `Run.collect_training_data`.
2. **What is recorded.** One `TrainingSample` per code-producing model attempt (codegen, fixer and other roles that answer with a patch envelope), written after the tamper gate and the ladder have judged it: target and dialect, story kind, task and node, role, attempt number, provider, model and model hash, whether the provider is local, the `LevelResult`s, and `improves_on_seq` linking a retry to the failed attempt it fixes. The verdict is computed from the oracle results, never set by a model (invariant 1): `rejected` if a level failed, `accepted` only if none failed and at least one passed, otherwise `not_verified`. Deterministic nodes produce no samples.
3. **Where and how.** Local files under the dataset directory, gitignored, never uploaded by barthelona: `samples.jsonl` holds the metadata, and the prompt and response texts are content-addressed files `texts/<aa>/<sha256>.txt` referenced by hash. Code therefore never travels inside the JSON (invariant 5), and shared prompt blocks are stored once. A text is written before the index line that references it.
4. **Redaction.** Before a text is written, the values of the configured API keys and anything shaped like a provider key are replaced with `[REDACTED]` (invariant 10).
5. **Never the holdout.** `SampleSource` is `run` or `bench_dev`; holdout benchmark attempts cannot be labelled as such, `source` has no default, and the Phase 1 engine hook refuses to record a run on a holdout task (testing policy: the holdout is never shown to a model).
6. **Separate from the app database.** The dataset is not a table in `var/app.sqlite`: it outlives app-database resets and can be copied or archived as one directory.

## Rationale
- Opt-in and local follows local-first operation and the cloud-egress control in §21: nothing leaves the machine, and nothing is collected unless the owner asks.
- Labels from the oracles are the only trustworthy ones; LLM review is advisory (§2, principle 1).
- Recording at the attempt level, with the retry link, yields supervised pairs (accepted attempts) and preference pairs (rejected → accepted) from the same data.
- Content-addressed texts keep the index small and respect invariant 5; the export format for a trainer is chosen when training starts.

## Alternatives considered
- Reuse `var/runs/<id>/llm/*.json`: no verdict, one directory per run, purged with the run; a dataset would need a join over every run anyway.
- A table in `var/app.sqlite`: couples the dataset to the app schema and its migrations, and puts code into SQLite JSON columns.
- Record every LLM call (planner, spec, review): most are not assembly code and have no oracle label; they can be added later as their own sample kinds.
- On by default: collects prompts and code the owner did not decide to keep, and cloud outputs whose provider terms the owner has not checked.

## Consequences
- Each sample records `provider` and `local`. Provider terms may limit using cloud model outputs to train other models; the export (Phase 1, roadmap) keeps only local-model samples unless the owner opts in for a provider after checking its terms.
- The disk use grows with runs; `barthelona training status` shows the count, and deleting the directory removes the dataset.
- Phase 0 ships the models, the settings, the writer and reader, and `training status`; the engine hook, the UI checkbox and the export arrive in Phase 1 (roadmap).
