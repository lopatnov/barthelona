# Current Status: What Works Today (2026-10-24)

This page says what you can run today, in plain words, with one-line commands that paste straight into PowerShell
(the same lines work in Git Bash and Linux shells unless a note says otherwise). Anything not listed under
"What does not work yet" is covered by a test or was run by hand; where something is only a library with no command,
the text says so.

Contents: [1 Quick start](#1-quick-start) · [2 Commands](#2-commands) · [3 Model gateway](#3-model-gateway) ·
[4 Training data](#4-training-data-collection) · [5 Verification](#5-verification-test-projects-that-pass-today) ·
[6 Code generation](#6-code-generation-no-llm) · [7 Create a project](#7-create-a-project-worker-streamlit-ui-and---project) ·
[8 Not yet](#8-what-does-not-work-yet) · [9 Environment](#9-environment) · [10 Layout](#10-layout)

Integration guides: [Meterless](meterless-guide.md) · [Zetaris](zetaris-guide.md) ·
[Hackathon demo](hackathon-demo-guide.md) · [Create flow](create-flow.md)

## How the pieces fit together

Barthelona builds a program from a request like "write a NASM strlen function". Models propose; tools decide.

| Piece | What it is | Where it acts |
| --- | --- | --- |
| **Meterless (Nightshift runtime)** | The service that answers every model call. It routes a request to a model lane (`auto`, `deep`, `fast`), here free Nemotron models. | All LLM calls of the `meterless` profile |
| **Markovian chunks** | A long task is split into bounded chunks. Each chunk gets only a short carried-over summary, so the context never grows without limit. | `chunked run` and the worker's code-writing step |
| **H-MEM** | A small SQLite memory of facts and past results. Before every chunk the best matches are recalled; when the assembler and emulator accept a program, what was learned is written back. | Same two places |
| **Zetaris** | A SQL engine holding the knowledge tables (assembly facts) and, after `zetaris publish`, run history. Its rows are fed to the models as untrusted facts and seed H-MEM. | `zetaris`, `--facts-sql`, the worker |
| **World Model** | Event-sourced shared state for agents running in parallel (TypeScript, `engines/world-model`). **Not used by the pipeline yet** and its conformance run is not done. | Nowhere yet |
| **Oracles** | NASM (assembler), the Unicorn emulator, and for projects `ld`, `nm`, gcc in a Docker container. They accept or reject. | Verification |

---

## 1. Quick start

```powershell
.\scripts\create_env.ps1
```

```powershell
. .\scripts\activate.ps1
```

```powershell
.\scripts\doctor.ps1
```

The first line creates the conda env `barthelona` (Python 3.13) with locked dependencies. The second activates it
(note the leading dot). The third checks the setup. Optional: `copy .env.example .env`, then add keys. Git Bash and
Linux: `scripts/create_env.sh`, then `source scripts/activate.sh`. Full setup: [runbook](runbook.md).

---

## 2. Commands

Run `python -m barthelona --help` for the list. "Needs" says what must be running.

| Command | What it does | Needs |
| --- | --- | --- |
| `version`, `schema` | Print the version; print the JSON schema of a data document | nothing |
| `probe` | Record the exact tool versions of the build container | Docker (`bart-tc`) |
| `verify` | Check an assembly project with the verification ladder | Docker (`bart-tc`, `bart-run`) |
| `check` | Assemble one NASM file and run its golden tests in the emulator | `nasm` only, no Docker |
| `meterless status`, `zetaris status` | Say whether the service is online, unauthorized or offline | the service |
| `zetaris sql` / `seed` / `publish` | Query Zetaris; copy its knowledge into H-MEM; copy run history into it | Zetaris |
| `chunked run` / `stats` | Run one task in Markovian chunks; show statistics | a model endpoint |
| `worker`, `runs ...` | The create flow, see [section 7](#7-create-a-project-worker-streamlit-ui-and---project) | a model endpoint |
| `training status` | Show the training-data setting ([section 4](#4-training-data-collection)) | nothing |
| `bench ...` | Benchmark library commands (see `--help`) | a model endpoint |

### 2.1 `probe`: the toolchain lock file

**What problem it solves.** Builds must be repeatable. Today "assembles on my PC" can silently stop being true
because a tool such as `nasm` was upgraded. `probe` asks the build container which tools it contains and writes
their exact versions and paths, plus the container image digests (the image's fingerprint), into one file,
`config/toolchains.lock.json`. That file is the **toolchain lock file**: a snapshot saying "this project was checked
with nasm X, ld Y, gcc Z in image W". It is committed to git; if the tools change, the diff shows it. Later
phases refuse to trust results when the file and the container disagree. Today the file exists and is written by
`probe`; the toolchain image digest is still empty (open item in the roadmap).

```powershell
python -m barthelona probe
```

Prints the version and path of each tool (nasm, yasm, fasm, as, ld, gcc, gdb, make) and writes the lock file.
`--output PATH` (or `-o`) writes it elsewhere; `--transport auto|wsl|local` chooses how to reach Docker (see 2.2).
Prerequisite: the `bart-tc` container is running; one command builds and starts it:
`wsl -d Ubuntu -e bash scripts/setup-toolchain.sh` (Windows) or `scripts/setup-toolchain.sh` (Linux).

### 2.2 `verify`: check an assembly project

**What it does.** Takes a folder of assembly files and runs the **verification ladder**: a series of checks from cheap
to expensive. The first failure stops the climb and is reported. The tools run inside Docker, never on your host.

**Which OS.** The command itself runs on Windows (through WSL2 Ubuntu with Docker) and on Linux (Docker directly).
macOS is not tested. `--transport auto` picks WSL on Windows and the local Docker on Linux; force it with
`--transport wsl` or `--transport local`. Test projects are Linux x86-64 programs (ELF) in both cases.

Demonstration, one line (needs the `bart-tc` container from 2.1):

```powershell
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm --contracts tests/projects/nasm-triple/contracts.yaml --tests tests/projects/nasm-triple/tests.yaml
```

Expected: a table with V0, V1, V2, V5 and V6 each `pass`, and exit code 0. Check with `$LASTEXITCODE` in PowerShell or
`echo $?` elsewhere. To see a failure on purpose, copy the folder, change one instruction in `math.asm`, and run again.

The options and why they exist:

| Option | Meaning | Why |
| --- | --- | --- |
| `WORKSPACE` | Folder with the `.asm` or `.s` files | What to check |
| `--level`, `-l` | Highest ladder level to run (default `V2`) | Stop early for speed; use `V6` for everything |
| `--dialect`, `-d` | `nasm`, `gas-intel` or `gas-att` | Guessed from file extensions; give it for Intel-syntax GAS |
| `--contracts`, `-c` | `contracts.yaml`, the interface list | V1 then also compares each module's exported symbols with it; also runs the tamper gate on `gen/` |
| `--tests`, `-t` | A YAML list of test cases | V5 and V6 need them |
| `--require` | Levels that must pass, e.g. `V0,V1,V2,V5,V6` | Other unsupported levels are reported but do not fail the run |
| `--json` | One JSON document on stdout | For scripts and CI |
| `--run-id` | Name of the staging folder | Keep runs apart |
| `--transport` | `auto`, `wsl`, `local` | See "Which OS" |

The levels:

| Level | Check | Status |
| --- | --- | --- |
| V0 | Syntax only (assembler without output) | works |
| V1 | Assemble each module; `nm` symbols match the contracts | works |
| V2 | Link; no unresolved or duplicate symbols, entry point present | works |
| V3, V4 | Static and dynamic ABI checks (Capstone, Unicorn) | libraries exist; not ladder levels yet |
| V5 | C test harness calls each function with set inputs (in `bart-run`) | works |
| V6 | Whole program: run it and compare stdout and exit code with the golden test | works |
| V7, V8 | Debugger trace; real Windows | planned |

The **tamper gate** checks that generated files in `gen/` still match the contracts and that tests were not edited
while coding. The minimality gate (edit mode) is also in the code.

### 2.3 `meterless status`: is the model service reachable

```powershell
python -m barthelona meterless status
```

Needs `METERLESS_BASE_URL` (default `http://127.0.0.1:8088/v1`) and `METERLESS_RUNTIME_TOKEN` set in your environment.
Prints `online`, `unauthorized` (bad token) or `offline`, and the `meterless/*` routes. `--url` overrides the address
(a connect link also works). The routes are mapped to roles in `config/models.yaml`:

| Role | Chain (profile `meterless`) | Used for |
| --- | --- | --- |
| main, worker | `meterless/auto`, then local model | the answers of each chunk, code |
| planner | `meterless/deep`, `auto`, local | plans, spec and tests (strongest lane) |
| cheap | `meterless/fast`, `auto`, local | reviews, summaries |
| escalation | `meterless/deep`, local | repairs that keep failing |

More in the [Meterless guide](meterless-guide.md).

### 2.4 Zetaris: `status`, `sql`, `seed`, `publish`

Needs `ZETARIS_API_KEY` in your environment. Optional: `ZETARIS_REST_URL` (default `http://localhost:8888/api/v1.0`),
`ZETARIS_ORG_ID` (default `1`).

```powershell
python -m barthelona zetaris status
```

```powershell
python -m barthelona zetaris sql "SELECT * FROM my_table LIMIT 10"
```

`sql` sends one read-only statement (`SELECT`, `SHOW`, `DESCRIBE` or `WITH`) and prints the rows; `--limit N`
(default 50, up to 1000) caps them. Replace `my_table` with a real table: list them with
`python -m barthelona zetaris sql "SHOW TABLES"`. The knowledge tables Barthelona registers are described in
[`docs/zetaris-engines.md`](zetaris-engines.md) and `knowledge/zetaris/`.

```powershell
python -m barthelona zetaris seed --memory var/hmem.sqlite
```

Turns the registered knowledge tables into H-MEM memories (`--domain` defaults to `assembly`), so chunked runs recall them.

```powershell
python -m barthelona zetaris publish <driver-container> --runs-db var/runs.sqlite --hmem-db var/hmem.sqlite
```

Copies run statistics and H-MEM into Zetaris as tables (SQLite stays the store; safe to repeat). Replace
`<driver-container>` with the name from `docker ps`. More in the [Zetaris guide](zetaris-guide.md).

### 2.5 `chunked run`: one long task in Markovian chunks

One line, ready to paste:

```powershell
python -m barthelona chunked run "Write a NASM strlen function" --out strlen.asm --code --assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite
```

The model service must be reachable (2.3). `--profile meterless` and `--role worker` are the defaults, so they are
left out. The task text can also come from a file: `chunked run @task.txt`. Steps it takes:

1. Recall memories from H-MEM (`--memory`) and, if `--facts-sql` is given, rows from Zetaris.
2. Optionally write a short plan with `--plan-role` (for example `planner`).
3. Run the task in bounded chunks, passing a short summary from chunk to chunk.
4. With `--assemble`, assemble the code with NASM. On failure, retry up to `--repair` times with the assembler's errors.
5. Optionally review with `--review-role`. The review is advice; the assembler decides.
6. If the assembler accepted, write the lesson to H-MEM; record per-chunk statistics in `--stats`.

Options:

| Option | Default | Meaning |
| --- | --- | --- |
| `TASK` | required | The task text, or `@file` |
| `--profile` | `meterless` | Which set of model chains: `meterless`, `local-only`, `hybrid`, `cloud` |
| `--role` | `worker` | Which role's chain answers each chunk |
| `--out FILE` | none | Write the result to this file |
| `--code` | off | Write only the fenced code blocks, not the prose |
| `--assemble` | off | Assemble with NASM; the run is green only if it assembles (implies `--code`) |
| `--repair N` | 0 | With `--assemble`: up to N more attempts (0 to 3) that get the errors back |
| `--repair-role` | none | Role used for those attempts, e.g. `planner` |
| `--expect-stdout`, `--expect-exit` | none | Also run the program in the emulator and require this output and exit code |
| `--memory FILE` | none | H-MEM database: recall before chunk 1, write at the end |
| `--domain` | `assembly` | Tag used to rank and label memories |
| `--facts-sql` | none | One read-only Zetaris statement; rows go in front of chunk 1 as untrusted facts |
| `--plan-role`, `--review-role` | none | Roles that write a plan first or review at the end |
| `--stats FILE` | none | SQLite file for run statistics |
| `--chunk-tokens`, `--carryover-tokens`, `--max-chunks` | 8000, 800, 24 | Chunk size, summary size, chunk cap |
| `--single-shot` | off | One completion instead of chunks (short tasks) |
| `--nasm` | auto | Path of the `nasm` binary |

Show the statistics afterwards (calls, tokens, time per model):

```powershell
python -m barthelona chunked stats --db var/runs.sqlite
```

The exit code is non-zero unless the run completed.

---

## 3. Model gateway

`src/barthelona/llm/gateway.py` is the one door between Barthelona and models. What it does today (checked against
the code):

- **Role router.** Each role (main, planner, worker, cheap, escalation) has an ordered chain in `config/models.yaml`; the
  gateway tries them in order. Every chain ends in the local model.
- **Fallback.** A call that fails (timeout, rate limit, empty reply) moves to the next model in the chain; the event is
  recorded, not raised.
- **Retries.** Rate limits and transient errors are retried twice, after 2 s and 6 s, honouring `Retry-After`
  up to 30 s.
- **Limits per service.** At most `max_concurrency` calls at once per provider (local endpoints: one).
- **Backend.** One backend is implemented: `OpenAIChatBackend`, the OpenAI-compatible chat API. It serves LM Studio,
  Ollama, Meterless, DeepSeek and Qwen Cloud. `FakeGateway` replaces it in tests.
- **Ledger.** Calls made by the worker are written to the run's LLM-call ledger in SQLite.

**Not implemented yet** (an earlier version of this page claimed them): Anthropic, OpenAI Responses and Gemini
backends (the catalog accepts these provider kinds, nothing serves them), circuit breakers, a cost ledger with
price tiers, structured-output modes beyond the chat API, a model-affinity scheduler, streaming, and
reserve-then-settle budgets. They are planned in `docs/roadmap.md` and architecture section 16.

---

## 4. Training data collection

**Purpose.** Every proposal a model makes, together with the verdict of the tools (accepted or rejected), is
potential training data for fine-tuning a local model later. Collection is **off by default** and local.

**What exists today.** Only the library: `src/barthelona/training/` can write samples (a `samples.jsonl` index plus
prompt and reply texts under `texts/`, secrets redacted) and read them back. **No run records samples yet.** Nothing
in the worker or `chunked run` calls the writer, and there is no `training export` command. Both are planned (roadmap
F-81, D-051, Phase 1b). Tracked in the issue linked from the roadmap Follow-ups.

The one command that works:

```powershell
python -m barthelona training status
```

It prints whether collection is enabled, the directory, and the number of samples per verdict (`accepted`,
`rejected`, `not_verified`; all 0 today). To switch the setting on in the current PowerShell session
(it only has an effect once the engine records samples):

```powershell
$env:BARTHELONA_TRAINING_DATA_ENABLED = "1"
```

**Intended sequence, once wired:** enable the setting, submit a run (`runs submit`, section 7), let it finish,
run `training status` to see the new samples, then `training export` writes trainer-ready files. Where it will
look: `var/training/` unless `BARTHELONA_TRAINING_DATA_DIRECTORY` says otherwise.

---

## 5. Verification: test projects that pass today

Two hand-written three-module projects in `tests/projects/` are the fixtures for the ladder. They are test inputs for
the checker, not demos of the builder.

| Project | Dialect | Modules |
| --- | --- | --- |
| `nasm-triple` | NASM | `main.asm`, `io.asm`, `math.asm` |
| `gas-triple` | GAS Intel syntax | `main.s`, `io.s`, `math.s` |

Each folder has `contracts.yaml` (the functions and their registers and stack rules) and `tests.yaml` (V5 harness
calls and V6 whole-program output). The `gen/` folder next to them is generated from
`contracts.yaml` (section 6) and committed; `verify --contracts` stops at the tamper gate if it is missing or edited. They target **Linux x86-64**. Docker runs on Linux natively or inside WSL2 on
Windows, so the same command works on both hosts (see 2.2 for the OS rules).

NASM:

```powershell
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm --contracts tests/projects/nasm-triple/contracts.yaml --tests tests/projects/nasm-triple/tests.yaml
```

GAS:

```powershell
python -m barthelona verify tests/projects/gas-triple --level V6 --dialect gas-intel --contracts tests/projects/gas-triple/contracts.yaml --tests tests/projects/gas-triple/tests.yaml
```

Option meanings are in the table in 2.2. Continuous integration runs the unit tests only; it does not start Docker.

---

## 6. Code generation (no LLM)

**What it is.** Interfaces between assembly modules are easy to get wrong: a wrong register, a misspelt symbol, a
wrong struct offset. Barthelona therefore keeps one file, `contracts.yaml`, as the single source of truth for every
function, constant and struct. From it, plain deterministic code (no model) produces the glue, so nobody, human or
model, writes it by hand:

- `gen/<module>.inc`: what a module exports and imports.
- `gen/stubs/<module>.asm`: a skeleton in which every exported function traps (`ud2`); the all-stub project must
  assemble and link, which proves the interfaces fit before any real code exists.
- `gen/contracts.h`: C prototypes, constants, struct offsets, for the V5 harness.
- `gen/harness/<test>.c`: a C program that calls a function with given inputs and exits 1 on a mismatch.

**Why.** Models then only write function bodies against fixed interfaces, and the oracles can tell exactly what is
wrong. The **tamper gate** regenerates `gen/` from the contracts and flags any missing, edited or extra file, so a
model cannot quietly weaken the harness.

**How to enable it.** There is no switch and no command: `verify --contracts contracts.yaml` runs it (tamper gate
first, then the ladder with the generated harnesses). The library is `src/barthelona/contracts/codegen.py`. The
current single-module create flow does not use contracts yet (no architect step); the multi-module engine will.
A `Makefile` is planned, emitted by the `header_gen` node in Phase 1b.

---

## 7. Create a project: worker, Streamlit UI and `--project`

The create flow turns a request into one NASM program. The graph is `preflight`, `intake` (language, English goal,
entities), `spec`, `test_author` (golden-output tests), `validate_spec` (every requirement has a test), then
**gate G1** where you approve or reject the spec and tests. `approve` starts `codegen`: Markovian chunks, with
Zetaris facts and an H-MEM recall in each chunk, write one file; NASM assembles it and the Unicorn emulator runs
every golden test. A rejected program is sent back with the report up to twice. An accepted one is saved as
`var/runs/<run_id>/main.asm` and shown at **gate G4**; `approve` there ends the run as `green`. If every attempt is
rejected, the run stops as `max_attempts`. Not built: architect, contracts, sprint loop, so results are not
ABI-verified.

### The Streamlit UI

Start the worker and the UI together:

```powershell
.\scripts\run.ps1
```

Open http://127.0.0.1:8501. Flags: `-UiOnly`, `-WorkerOnly`, `-StreamlitPort 8502`. Linux and WSL: `scripts/run.sh`.
Pages: **New Request** (fill in and submit), **Approvals** (the gates G1 and G4 of a run), **Live Run** (progress).
The UI is a walking skeleton and still needs polish (roadmap F-115, issues #269 and #271); for example it cannot
package a run yet.

New Request fields:

- **Model profile.** `Meterless` (the free Nemotron lanes through the Meterless runtime; the default), `Local only`,
  `Hybrid`, `Cloud`. `--profile meterless` on the command line is the same choice as the first radio button.
- **Project folder.** The name of a subfolder of `demos/` (pick one or type a new lowercase name such as `my-strlen`).
  The finished project is packaged there; see `--project` below.
- **Budget.** Wall time (default 3600 s) and token budget (default 400,000), the same defaults as `runs submit`.
  These two limits are required by design: invariant 6 says every loop is bounded and every stop has a stop reason, so
  a run that cannot be stopped would be a defect. They are only ceilings; a run that finishes early uses less. The
  dollar cap is optional (0 means none; spending is metered either way).

### The same flow from the command line

```powershell
python -m barthelona worker
```

In another terminal:

```powershell
python -m barthelona runs submit "Print the digits 1 to 9, one per line" --project digits
```

```powershell
python -m barthelona runs status
```

```powershell
python -m barthelona runs decide <run_id> approve
```

`runs submit` queues the request (add `--profile`, `--wall-s`, `--tokens`, `--preset`); `runs status` lists runs or shows
one; `runs decide` answers the open gate (`approve` or `reject`; reject stops the run as `human_abort`). Use
`worker --once` to run what is queued and exit.

**`--project NAME`.** Names the folder under `demos/` where this run's result goes (a lowercase slug of letters,
digits and `-`, up to 41 characters). It is stored with the run, so the UI and the command line agree. When the run
is green, package it:

```powershell
python -m barthelona runs package <run_id> --barthelona-ref <full-commit-sha>
```

This writes the source, the golden tests, a README, CI and a release workflow into `demos/NAME/`
(`--out` chooses another folder; `--force` overwrites existing files). `--barthelona-ref` is the commit of Barthelona that
the generated CI installs. Without `--project` the run has no home folder and `--out` is required. Check any NASM file by hand:

```powershell
python -m barthelona check strlen.asm --tests tests/golden.json
```

---

## 8. What does not work yet

| Feature | Phase |
| --- | --- |
| Meta-Agentic Scrum: architect, sprint loop, AI-composed graphs, `fixer`, `sprint_planner` | 1 |
| Several modules, contracts in the create flow, gates G0, G2 to G6 | 1 |
| Recording training samples and `training export` | 1b |
| Compounding proof (a second run needing fewer chunks thanks to H-MEM) | open, issue #246 |
| World Model in the pipeline, conformance run | after Phase 1b |
| ABI checks V3 and V4 as ladder levels | 2 |
| Edit mode for existing projects | 3 |
| FASM, Win64, ELF32, other assemblers | 4 |
| Policy lab, web research | 5 |
| C, web and 2D target families | 6 |
| Pure-assembly TLS and HTTP/2 proxy (the ambition bar) | 7 |

---

## 9. Environment

| Component | Windows | Linux |
| --- | --- | --- |
| Python | 3.13 (conda env `barthelona`) | 3.13 (conda) |
| Docker | inside WSL2 Ubuntu | native |
| LM Studio (local models) | `http://127.0.0.1:1234/v1` | same, or another PC |
| Meterless | `http://127.0.0.1:8088/v1`, `METERLESS_RUNTIME_TOKEN` | same |
| Zetaris | REST `:8888`, UI `:3000`, `ZETARIS_API_KEY` | same |
| Qdrant (project) | `docker/qdrant/compose.yaml` in WSL | same compose file |

Local models need a WSL memory cap in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=8GB`, `processors=8`), then
`wsl --shutdown`. Secrets come only from environment variables; never commit `.env`.

---

## 10. Layout

```
config/       models.yaml (models, role chains, budgets), toolchains.lock.json (written by probe)
docker/       toolchain (bart-tc), runner (bart-run), qdrant
engines/      world-model (TypeScript, not used by the pipeline yet)
knowledge/    Zetaris knowledge tables
src/barthelona/
  cli/ domain/ engine/ executors/ toolchains/ verification/ contracts/ emulator/
  llm/ (gateway, catalog, Meterless, Zetaris, Markovian, H-MEM)  persistence/  training/  ui/
tests/        unit tests, projects/ (nasm-triple, gas-triple), abi_mutation/, fixtures/
demos/        one subfolder per finished project (submodules for the planned demos)
var/          gitignored: app.sqlite, runs/, hmem.sqlite, runs.sqlite, training/
```

Next steps: [architecture](architecture.md), [roadmap](roadmap.md).
