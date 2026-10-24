# The create flow: commands and flags

How to turn a request into a checked, packaged assembly project with the worker. Every command below is
`python -m barthelona <command>`. Agents and tools without the conda env prefix it with
`.\scripts\dev.ps1` or `scripts/dev.sh`. Add `-LoadEnv` as the first argument to export the keys from `.env`
for that one command (`.\scripts\dev.ps1 -LoadEnv python -m barthelona worker`); without it the command sees
only the variables already set in the shell. Secrets come only from environment variables.

## The steps

1. Start the worker and leave it running: `python -m barthelona worker`.
2. Queue a run: `python -m barthelona runs submit @prompt.txt --profile meterless`. It prints the run id.
3. The worker writes the specification and the tests, then parks the run at gate **G1**. Read them with
   `runs status <run_id>` (or in the Streamlit UI) and answer with `runs decide <run_id> approve` or
   `reject`. The tests are frozen after G1, so check them against the specification first.
4. The worker generates the code, assembles it with NASM and runs the tests in the emulator. It parks at
   gate **G4** with a verdict. Answer with `runs decide <run_id> approve` or `reject`.
5. For a green single-module run: `runs package <run_id> --out <folder> --barthelona-ref <commit sha>` writes
   the source, tests, README, CI and release workflow. `check <source>` repeats the emulator check anywhere.

## Commands

| Command | What it does | Flags |
| --- | --- | --- |
| `worker` | Claims queued runs, runs them to the next gate, continues them after a decision | `--db`, `--checkpoints`, `--runs`, `--catalog`, `--facts-sql`, `--memory`, `--poll`, `--once`, `--trace-reasoning` |
| `runs submit REQUEST` | Queues a create-mode run (`@file` reads the request from a file) | `--profile`, `--preset`, `--wall-s`, `--tokens`, `--db`, `--runs` |
| `runs status [RUN_ID]` | Lists runs, or shows one run's state, open gates and last events | `--db`, `--runs` |
| `runs decide RUN_ID DECISION` | Answers the open gate (`approve` or `reject`) | `--db` |
| `runs package RUN_ID` | Writes the repository files of a green single-module run | `--out` and `--barthelona-ref` (required), `--force`, `--db`, `--runs` |
| `check SOURCE` | Assembles with NASM and runs the golden tests in the emulator; exit 1 unless all pass | `--tests` (default `tests/golden.json`) |

Defaults: `--db var/app.sqlite`, `--runs var/runs`, `--checkpoints var/checkpoints.sqlite`,
`--catalog config/models.yaml`, `--profile meterless`, `--preset linux-x64-nasm-static`, `--wall-s 3600`,
`--tokens 400000`. `--memory` defaults to `hmem.sqlite` next to `--db`. `--facts-sql` replaces the Zetaris
statement behind the facts in the prompts; by default, with `ZETARIS_API_KEY` set, the Barthelona knowledge
tables are used. `--profile` is one of `local-only`, `hybrid`, `cloud`, `meterless`. Run any command with
`--help` for the current list.

## Watching what the models think

`worker --trace-reasoning run-reasoning.md` appends one entry per answered model request to that file: the
role, the model, tokens, seconds, the model's reasoning and its answer. `--trace-reasoning -` prints the
entries to stderr instead. `chunked run` has the same flag. The reasoning comes from the provider's separate
reasoning stream or from `<think>` blocks in the reply; when a model sends neither, the entry says so.
The log is off by default and holds the request text and the models' answers, so keep it out of git.

## Environment variables

| Variable | Used for |
| --- | --- |
| `METERLESS_RUNTIME_TOKEN` | The Nightshift runtime access token (profile `meterless`) |
| `ZETARIS_API_KEY` | The Zetaris REST API behind the facts and the H-MEM seed |
| `BARTHELONA_NASM`, `NASM_PATH` | The nasm binary, before `PATH` |
