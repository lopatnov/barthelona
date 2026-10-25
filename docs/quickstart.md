# Quickstart: install, run, and what works today (2026-10-24)

Barthelona turns a request written in plain language into a small assembly program and checks it with real tools
instead of trusting the model. This page is both the quickstart and the status page: how to install, what you can run today, what each command is
for, what you should see, and what does **not** work yet. Every command was run on the Windows development PC on 2026-10-24 unless the text
says otherwise. For the live runs and what they proved, read the
[hackathon demo guide](hackathon-demo-guide.md#where-it-stands); for the design, [architecture.md](architecture.md).

> **Integration guides:** [`docs/meterless-guide.md`](meterless-guide.md) | [`docs/zetaris-guide.md`](zetaris-guide.md) | [`docs/hackathon-demo-guide.md`](hackathon-demo-guide.md) | [`docs/create-flow.md`](create-flow.md)

**Where the technologies fit.** Models are called through Meterless Nightshift (free NVIDIA Nemotron lanes),
Zetaris supplies the syscall and ABI facts that go into the prompts, and the H-MEM memory and Markovian chunk loop
keep long answers bounded. The table is in [architecture.md section 3.1](architecture.md#31-where-the-hackathon-technologies-sit-in-the-pipeline).

## Words used on this page

| Word | Meaning |
| --- | --- |
| **Assembler / NASM / GAS** | The program that turns assembly text (`mov rax, 1`) into machine code. NASM and GNU `as` (GAS) are two of them. |
| **Linker (`ld`)** | Joins the machine code of several files into one program that can start. |
| **Toolchain** | The set of programs used to build and check code: the assembler, the linker, `gcc`, `gdb`, `make`. They run inside a Docker container so every PC gets the same versions. |
| **Oracle** | A tool that decides whether code is acceptable (assembler, linker, emulator, tests). Models only propose; oracles decide. |
| **Emulator (Unicorn)** | A small virtual CPU. A generated program is run inside it, never on your PC, and its output and exit code are compared with the expected ones. |
| **Golden test** | A test that says: for this input the program must print exactly this and exit with this code. |
| **Gate (G1, G4)** | A point where a person approves: G1 the specification and tests, G4 the finished code. |
| **Profile, role, route** | The profile `meterless` is the set of model chains in `config/models.yaml`. A role (`main`, `worker`, `planner`, `cheap`) picks a chain from it. A route (`meterless/auto`, `deep`, `fast`) is what Nightshift is asked for. |
| **Chunk, H-MEM** | A long answer is produced in bounded pieces (chunks) so the prompt does not grow. H-MEM is the memory that is recalled before each chunk. |

---

## 1. Quick start (Windows PowerShell)

```powershell
.\scripts\create_env.ps1
. .\scripts\activate.ps1
.\scripts\doctor.ps1
```

`create_env.ps1` creates the conda environment `barthelona` (Python 3.13) with hash-locked dependencies. The dot in
`. .\scripts\activate.ps1` matters. `doctor.ps1` checks the setup. Optional: `copy .env.example .env` and put keys in
`.env` (never commit it). Git Bash: `scripts/create_env.sh`, then `source scripts/activate.sh`. The toolchain
container is started once with `wsl -d Ubuntu -e bash scripts/setup-toolchain.sh`; see [runbook.md](runbook.md).

**NASM** (needed by `chunked run --assemble` and `check`): install it from https://www.nasm.us/. It is found through
`--nasm`, `BARTHELONA_NASM`, `NASM_PATH` (a file or its folder), `PATH`, then the usual Windows folders.

**Meterless Nightshift** (the hackathon model provider; it routes to local and cloud lanes):

1. Install the Nightshift app from https://meterless.ai and start it. It serves an OpenAI-compatible endpoint at
   `http://127.0.0.1:8088/v1`.
2. In Nightshift, Setup, Providers: add your NVIDIA key (free endpoint). The key lives only there, never in `.env`.
3. NIGHT, LANES: add at least a Race lane with a Nemotron model (follow Nightshift's own model list) and, to clear the
   red warning, a Judge or Verify lane on a different model: a model never grades its own answers.
4. Copy the runtime token from the Nightshift Console into `.env` as `METERLESS_RUNTIME_TOKEN` (`METERLESS_BASE_URL`
   only if the URL differs). Check with `python -m barthelona meterless status` (section 2.4).

Full guides: [meterless-guide.md](meterless-guide.md) and [zetaris-guide.md](zetaris-guide.md).

Optional: LM Studio or Ollama as the local last fallback (the `meterless` profile ends in the local model, so a failed
cloud call can silently fall back; stop it to see the real errors), WSL2 + Docker for `verify` and `probe`, Qdrant
and Zetaris (Docker with 8 GB RAM).

Tools without the environment (an agent shell, a script) put `.\scripts\dev.ps1` in front of a command, and
`.\scripts\dev.ps1 -LoadEnv` also exports the keys from `.env` for that one command.

---

## 2. The commands

Run `python -m barthelona --help` for the list.

| Command | What it is for | Needs |
| --- | --- | --- |
| `version`, `schema` | Print the version; print the JSON schema of a data type | nothing |
| `probe` | Ask the toolchain container which tools and versions it has and write a lock file | Docker (WSL on Windows) |
| `verify` | Check an assembly project with the assembler, linker, symbol check and tests | Docker |
| `check` | Assemble one NASM file and run its golden tests in the emulator | NASM |
| `meterless status` | Is the Nightshift runtime reachable and does it accept our token | Nightshift |
| `zetaris status`, `zetaris sql`, `zetaris seed`, `zetaris publish` | Probe Zetaris, read from it, copy its facts into memory, copy run history into it | Zetaris |
| `chunked run`, `chunked stats` | Produce a program in bounded chunks, check it, and show statistics | a model endpoint |
| `worker`, `runs submit/status/decide/package` | The create flow: request, specification, tests, code, gates, repository files | a model endpoint |
| `training status` | Show the training-data setting and counts | nothing |
| `.\scripts\run.ps1` / `scripts/run.sh` | Start the worker and the Streamlit UI | the above |

### 2.1 `probe`: pin the toolchain versions

**What it is.** To check generated code, Barthelona uses a fixed set of programs (the *toolchain*: `nasm`, `as`, `ld`,
`gcc`, `nm`, `make`, `gdb`) that live in a Docker container named `bart-tc`. `probe` asks that container what it has and
writes the answer to `config/toolchains.lock.json`: each tool's exact version and the content hash (digest) of the
container image. A lock file like this is the same idea as a `package-lock.json`: it records exactly what was used.

**Why.** So a result can be repeated: "this program passed with NASM 3.01 and binutils 2.46" is a checkable claim.
Today nothing in a run reads the lock file yet (only `probe` writes it), so it is a record, not a switch.

```powershell
python -m barthelona probe --output var/proof/toolchains.lock.json
```

You should see the two image digests and one line per tool, for example `nasm: NASM version 3.01 at /usr/bin/nasm`.
Options: `--output/-o` (default `config/toolchains.lock.json`, which is tracked in git, so use another path for a
trial) and `--transport` (`auto`, or `wsl` on Windows). It needs Docker and the container: start it with
`wsl -d Ubuntu -e bash scripts/setup-toolchain.sh`.

### 2.2 `verify`: check an assembly project with real tools

**What it is.** `verify` runs a project through a ladder of checks, lowest first, and stops reporting a level as
passed only if the tool agrees. Run it on any folder of assembly files.

| Level | What is checked | State |
| --- | --- | --- |
| V0 | The syntax is accepted (assemble to nowhere) | works |
| V1 | Each file assembles; the symbols found by `nm` match the contract | works |
| V2 | The files link into one program: no missing or duplicate symbol, an entry point exists | works |
| V3 | Static ABI lint: calling-convention mistakes found by reading the machine code | a library, not yet a ladder level; `verify` prints "unsupported" |
| V4 | Dynamic ABI checks while the code runs in the emulator | a library, not yet a ladder level; `verify` prints "unsupported" |
| V5 | A C test program calls your functions with inputs and compares results (in a sandbox container) | works |
| V6 | The whole program runs with golden input and output (in a sandbox container) | works |
| V7, V8 | Trace after a failure; real Windows | planned |

Two more gates run in addition: the **tamper gate** (the generated `gen/` folder must be exactly what the contracts
produce, so nobody edits interfaces or tests by hand) and, for edits of existing projects, a **minimality gate**.

**A command to run** (works as written from the repository root):

```powershell
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm --contracts tests/projects/nasm-triple/contracts.yaml --tests tests/projects/nasm-triple/tests.yaml --require "V0,V1,V2,V5,V6"
```

**Expected:** `✓ tamper`, `✓ V0`, `✓ V1`, `✓ V2`, `✗ V3: unsupported`, `✗ V4: unsupported`, `✓ V5`, `✓ V6`, and exit
code 0. The GAS (GNU assembler, Intel syntax) project works the same way:

```powershell
python -m barthelona verify tests/projects/gas-triple --level V6 --dialect gas-intel --contracts tests/projects/gas-triple/contracts.yaml --tests tests/projects/gas-triple/tests.yaml --require "V0,V1,V2,V5,V6"
```

**Why the options.**

| Option | Why it is there |
| --- | --- |
| `--level` | The highest level to run (V0 to V6); lower levels always run first |
| `--dialect` | `nasm`, `gas-intel` or `gas-att`: which assembler syntax the files use |
| `--contracts` | The `contracts.yaml` with the declared symbols; it switches on the symbol check (V1) and the tamper gate |
| `--tests` | The test cases (`c_harness` for V5, `io_golden` for V6) |
| `--require` | Levels that must pass for exit code 0. Without it the unsupported V3 and V4 make the exit code 1. Quote the list in PowerShell |
| `--transport` | How to reach the container (`auto`; `wsl` on Windows) |
| `--json` | Print one JSON document instead of the table |
| `--run-id` | Name of the staging session |

Without `--contracts` and `--tests` only V0 to V2 can run: `python -m barthelona verify tests/projects/nasm-triple --level V2 --dialect nasm`.

### 2.3 `check`: assemble one file and run its golden tests

```powershell
python -m barthelona check path\to\program.asm --tests path\to\golden.json
```

NASM assembles the file and the Unicorn emulator runs every golden test (stdout and exit code must match). Output:
`<file>: pass (1 tests)`; exit code 1 unless all tests pass. This is what the CI file of a packaged project runs.

### 2.4 `meterless status`: is Nightshift reachable

```powershell
python -m barthelona meterless status
```

Prints `online` and the routes it offers (`meterless/auto`, `fast`, `deep`, and others), `unauthorized` for a wrong
token, or `offline`. The token comes from `METERLESS_RUNTIME_TOKEN` (`METERLESS_BASE_URL` only if it is not
`http://127.0.0.1:8088/v1`); in an agent shell add `-LoadEnv`. The catalog `config/models.yaml` maps our roles to routes:

| Role | Chain in the profile `meterless` |
| --- | --- |
| `main` (intake) and `worker` (code) | `meterless_auto`, then `local_main` |
| `planner` (spec, tests, repair) | `meterless_deep`, then `meterless_auto`, then `local_main` |
| `cheap` (the optional `--review-role` of `chunked run`) | `meterless_fast`, then `meterless_auto`, then `local_main` |
| `escalation` | `meterless_deep`, then `local_main` |

`local_main` is the local model in LM Studio; every chain ends with it. For a run that must not touch a local model,
use a copy of the catalog in which the `lmstudio` provider is `enabled: false` and pass it with `--catalog`. More in
[meterless-guide.md](meterless-guide.md).

### 2.5 Zetaris: `status`, `sql`, `seed`, `publish`

**What it is.** Zetaris is a data platform you ask with SQL. Barthelona keeps assembler facts there (two tables:
`barthelona_files.linux_x64_syscalls` with 37 rows and `barthelona_files.abi_facts` with 11), reads them into the
prompts, and can copy run history into it. It needs `ZETARIS_API_KEY` (and `ZETARIS_REST_URL`, `ZETARIS_ORG_ID` only if
they differ from `http://localhost:8888/api/v1.0` and `1`). Registering the tables is in [`knowledge/zetaris/README.md`](../knowledge/zetaris/README.md).

```powershell
python -m barthelona zetaris status
python -m barthelona zetaris sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls LIMIT 5"
python -m barthelona zetaris sql "SHOW LIGHTNING TABLES barthelona_files"
```

`status` prints `online`, `unauthorized`, `offline` or `unconfigured`. The first query prints rows such as
`write | rdi=fd | rsi=buf | rdx=count`; the second lists the two tables. `sql` sends exactly one `SELECT`, `SHOW`,
`DESCRIBE` or `WITH` statement and refuses anything else (it never writes). `--limit N` sets the number of rows.

```powershell
python -m barthelona zetaris seed --memory var/hmem.sqlite
python -m barthelona zetaris publish <driver container> --hmem-db var/hmem.sqlite --runs-db var/runs.sqlite
```

`seed` turns the facts into memory entries (48 on the first run, 0 on a repeat) so later runs recall them.
`publish` copies run history and memory into Zetaris tables (`barthelona_runtime.*`); `<driver container>` is the
name or id of the Zetaris driver container from `docker ps`. It is the only command that writes to Zetaris and is safe to repeat.

### 2.6 `chunked run`: a task as bounded chunks, checked by the oracles

**What it is.** One request goes to a model chain; a long answer is produced in chunks of bounded size, with a short
carried-over state between them, so the prompt stays flat. With `--assemble` the code is assembled (a program that does
not assemble is not green), and with `--expect-stdout` and `--expect-exit` it is also run in the emulator and must print
exactly that and exit with that code. A rejected program goes back to the model with the checker's message.

**The smallest useful command** (one line, copy it as it is):

```powershell
python -m barthelona chunked run "Write a NASM program for Linux x86-64 that prints hello and a newline, then exits with code 0" --single-shot --assemble --expect-stdout "hello\n" --expect-exit 0 --out var/hello.asm --trace-reasoning var/hello-reasoning.md
```

Expected: a one-row table, `stop_reason=green`, and `assemble: pass (it also ran in the emulator: stdout and exit code as expected)`.

**With memory, repairs and statistics:**

```powershell
python -m barthelona chunked run @demos/hello/task.txt --assemble --repair 2 --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 --memory var/hmem.sqlite --stats var/runs.sqlite --out var/hello.asm --trace-reasoning var/hello-reasoning.md
```

**With Zetaris facts for this one request:**

```powershell
python -m barthelona chunked run "Write a NASM program that prints Hello using the write syscall" --assemble --expect-stdout "Hello\n" --expect-exit 0 --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'" --out var/zeta-hello.asm
```

Then `python -m barthelona chunked stats --db var/runs.sqlite` prints the recent runs and the totals per model.

**Reading the output.** One row per chunk: which route was asked (`served by`), which model really answered
(`answered by`), tokens in and out, milliseconds, whether the model said it was done (`marker`) and where the carried
state came from. Then a summary line: `stop_reason` (`green` is done), `chunks`, `peak_prompt` (stays flat), and
`standard_cost`, `markovian_cost`, `efficiency` (how many input tokens chunking saved against keeping the full history;
`too short to compare` for a single chunk). Then `assemble: pass` or `fail` with the reason.

| Option | What it does and why |
| --- | --- |
| `task` | The request text, or `@file` to read it from a file |
| `--profile` (default `meterless`) | Which set of model chains to use |
| `--role` (default `worker`) | Which chain answers each chunk |
| `--out FILE`, `--code` | Write the result to a file; `--code` keeps only the fenced code (implied by `--assemble`) |
| `--assemble`, `--repair N` | Require that the code assembles; allow N (0 to 3) extra attempts that get the assembler's errors back |
| `--expect-stdout TEXT`, `--expect-exit N` | Run the program in the emulator and require this output (`\n` and `\t` are escapes) and exit code; implies `--assemble` |
| `--single-shot` | One answer instead of chunks, for short tasks |
| `--chunk-tokens`, `--carryover-tokens`, `--max-chunks` | Chunk size (default 8000), carried state (800) and the upper bound of chunks (24) |
| `--memory FILE`, `--domain NAME` | Recall from and write to this H-MEM store; the memory is written only after a green run |
| `--facts-sql "SELECT ..."` | One read-only Zetaris statement whose rows go in front of chunk 1 as untrusted facts |
| `--plan-role`, `--repair-role`, `--review-role` | Extra roles: a short plan first, the role for repairs, an advisory review afterwards (the oracles still decide) |
| `--stats FILE` | Save per-chunk statistics to a SQLite file |
| `--catalog FILE` | Use another model catalog (for example one with the local model disabled) |
| `--trace-reasoning FILE` | Append every model's reasoning and answer to a file (`-` prints to the terminal); on by default (`var/activity.md`), `off` disables it; keep the file out of git |
| `--nasm PATH` | The `nasm` program, if it is not found automatically |

### Logging agent activity: what is recorded and how to switch it on

Three records exist. The first two are on by default; run statistics need `--stats`.

| What | How to switch it on | Where it ends up | How to read it |
| --- | --- | --- | --- |
| **Reasoning log**: for every answered model request the role, the model, tokens, seconds, what it thought and what it answered | on by default for `worker` and `chunked run`; `--trace-reasoning FILE` picks another file, `-` prints to the terminal, `off` disables it | `var/activity.md` | open it; it holds task text and model answers, so keep it out of git |
| **Call ledger**: every model call of a run (provider, model, tokens in and out, time) | always on for the worker | table `llm_calls` in `var/app.sqlite` | `sqlite3 var/app.sqlite "SELECT model, COUNT(*), SUM(tokens_in), SUM(tokens_out) FROM llm_calls GROUP BY model"` |
| **Run statistics** of `chunked run`: runs, and per chunk who answered, tokens, latency, fallbacks | add `--stats var/runs.sqlite` | the SQLite file you name | `python -m barthelona chunked stats --db var/runs.sqlite` |

`runs status <run_id>` also shows a run's state, open gates and last events. `zetaris publish` copies the statistics
and memory into Zetaris tables so they can be queried with SQL. The examples in this document and in the demo guide
name `--trace-reasoning` and `--stats` explicitly so that the files land where the text says.

### 2.7 The create flow: `worker` and `runs`

A run takes a request through intake, specification, tests, gate **G1**, code generation, assembly and emulation, and gate
**G4**. Start the worker, queue a request, answer the two gates:

```powershell
python -m barthelona worker --trace-reasoning var/run-reasoning.md
python -m barthelona runs submit "Write a program that prints hello and a newline, then exits with code 0." --project hello-world
python -m barthelona runs status
python -m barthelona runs decide <run id> approve
python -m barthelona runs package <run id> --barthelona-ref <full commit sha>
```

Run the worker in its own terminal. `runs submit` prints the run id; `--project NAME` records `demos/NAME` as the folder
for the packaged repository (a lowercase name that does not exist yet). `runs status` shows the open gate; read
`var/runs/<run id>/spec.json` and `tests.json` before approving G1, because the tests are frozen after it (the gate itself also carries the spec and the tests). `--auto-approve` lets the worker answer G1 and G4 itself and logs every automatic answer; NASM and the emulator still decide whether the code is accepted. A queued Cancel stops a run even in the middle of a model call. When a run stops green the worker also writes the project into its `demos/` folder (source, golden tests, README, CI), using this checkout's commit for the generated CI; `--no-package`, or the unticked box in the UI, leaves that to the Package button or `runs package`. After G4 the run
ends `green`, and `runs package` writes source, tests, README, CI and a release workflow. All options, the defaults
(limits 3600 s and 400000 tokens) and the environment variables are in [create-flow.md](create-flow.md).
One-sentence programs went green this way on 2026-10-24; larger ones (an interactive quiz) did not.

### 2.8 The Streamlit UI

```powershell
.\scripts\run.ps1
```

starts the worker and the UI at http://127.0.0.1:8501 (`-UiOnly`, `-WorkerOnly` and `-StreamlitPort 8502` change that).
Three pages exist: **New Request**, **Approvals** (answer G1 and G4) and **Live Run** (the models' thinking and answers as they arrive, the events of a run, and for a run that stopped green a **Package** panel, see below). On New Request
you choose:

- **New project** (ticked by default): ticked creates a project in a new `demos/` folder, unticked edits an existing one;
  then the dialect and target preset and the request text;
- the **model profile**: Meterless (the default; Nightshift is the model router with its auto, deep and fast lanes),
  local only, hybrid, or cloud (only Meterless and local can answer today). Zetaris works with every profile: with
  `ZETARIS_API_KEY` set its assembler facts go into the prompts;
- the **Project**: for a new project the folder name to create under `demos/`, otherwise the list of existing folders;
  a run records it and `runs package` writes there;
- **limits**, collapsed and optional: wall time, token limit, sprints and a money cap (defaults 3600 s, 400000 tokens,
  10 sprints, no money cap). Every run is bounded, but you do not have to enter anything;
- cloud consent and the training-data checkbox (see section 4).

When you press **Create Run**, the UI takes you straight to **Live Run** with that run selected.

**Model reasoning (Live Run).** The panel shows the newest replies of the run, each with what the model thought and what
it answered, and refreshes by itself. The box "Show what the models think and answer" is ticked by default. The worker
writes the same text to `var/runs/<run id>/reasoning.md` (per run) and to `var/activity.md` (all runs), and prints it to its
own terminal window, with the model that answered (long thoughts and answers cut short). `worker` and `chunked run` do this
by default; `--no-show-reasoning` turns it off.

**Package panel (Live Run).** Select a green run: the panel shows the `demos/` folder it will write, a field for the full
commit sha of barthelona that the generated CI installs (filled from `git rev-parse HEAD`), and the button **Package into
demos/**. It writes the same files as `runs package` and lists them. It refuses a folder that already has files (pick
another project folder, or use `runs package --force` on the command line).

This is a walking skeleton. Still missing: the sprint board, the review page, the models and provider-health page and a
list of past runs.

---

## 3. The model gateway

The gateway (`src/barthelona/llm/gateway.py`) answers a request for a role. **What it does today:**

- walks the role's chain for the profile in order; an entry that cannot be used is skipped with a reason (a disabled
  provider, a missing key such as `DASHSCOPE_API_KEY`, a provider kind without a backend), and a failed call falls
  through to the next entry; every fall-through is shown (`chunk 1 fell through: ...`);
- repeats a temporary failure (for example the `404 provider_error` Nightshift sometimes forwards) on the same entry a
  bounded number of times with growing, randomised waits before it falls through (#255);
- allows only `max_concurrency` calls at a time per provider;
- has one real backend, `OpenAIChatBackend` (OpenAI-compatible Chat Completions): Meterless, LM Studio and Ollama use it;
  `FakeGateway` stands in for tests;
- asks for JSON through `json_schema` where a provider supports it, and the engine's steps (intake, spec, tests) read
  JSON replies and send a bad one back once;
- strips `<think>` blocks from models marked `strip_think`, records tokens and latency of every call (`var/app.sqlite`
  for runs, the `--stats` file for `chunked run`), and can log reasoning with `--trace-reasoning`.

**What does not exist yet:** backends for Anthropic, OpenAI (Responses API) and Gemini, so chain entries for them are
skipped with `no backend for ...` (#252); mapping of DeepSeek and DashScope reasoning parameters (they answer
`cloud reasoning parameters are not mapped yet`); circuit breakers; the cost ledger (prices are in the catalog, but no
spend is computed); the scheduler that groups calls by model; streaming; budget reservation. Earlier versions of this
page listed some of these as done; they were not.

---

## 4. Training data (opt-in, D-036)

**State today: the storage code exists, but nothing in a run writes to it, so no training data is collected.**

What exists: a writer and a reader for a dataset (`samples.jsonl`, one line per model attempt, with the prompt and answer
texts in `texts/<aa>/<sha256>.txt`), redaction of secrets before writing, the setting, and `training status`.
The setting is the process environment variable `BARTHELONA_TRAINING_DATA_ENABLED` (never read from `.env`), with
`BARTHELONA_TRAINING_DATA_DIRECTORY` for the folder (default `var/training`). The New Request checkbox only stores a flag
on the run. No code outside `src/barthelona/training/` calls the writer, and there is no `training export` command.

**What you can run:**

```powershell
python -m barthelona training status
```

It prints `collection: disabled (set BARTHELONA_TRAINING_DATA_ENABLED=1)` (or `enabled`), `directory: var/training` and
the number of samples per verdict (`rejected`, `accepted`, `not_verified`); all zero today.

**The intended sequence (not built):** set `BARTHELONA_TRAINING_DATA_ENABLED=1` and tick the checkbox for a run;
after a code step is judged by the oracles, the worker writes one sample per code-producing attempt with the verdict
(`rejected` if a level failed, `accepted` if none failed and one passed, `not_verified` otherwise); holdout benchmark
attempts and deterministic steps are never collected; `training status` then shows the counts and `var/training/` holds
the files; an export step would produce trainer-ready files. Connecting the worker to the writer is open work.

---

## 5. Verification test projects

Two hand-written three-module projects in `tests/projects/` pass the whole ladder on the development PC:

| Project | Dialect | Files |
| --- | --- | --- |
| `nasm-triple` | NASM | `main.asm`, `io.asm`, `math.asm` |
| `gas-triple` | GNU as, Intel syntax | `main.s`, `io.s`, `math.s` |

Each has `contracts.yaml` (declared symbols, structs, register and stack rules), `tests.yaml` (V5 C-harness tests and V6
golden-output tests), the source files, and a `gen/` folder generated from the contracts (section 6).

**Which systems.** The commands run on Windows 11 with WSL2 and Docker (tested, 2026-10-24) and on Linux with Docker
(the reference host; CI uses it). The checks themselves always run in Linux containers (`bart-tc` for the tools,
`bart-run` for the sandbox). macOS is untested. Prepare the containers once with
`wsl -d Ubuntu -e bash scripts/setup-toolchain.sh` (Linux: `scripts/setup-toolchain.sh`), then run the two commands of
section 2.2. The options and why they exist are explained there. The same projects are also the `docker`-marked tests
(`python -m pytest -m docker tests/unit/verification/test_projects.py`, run by CI on Linux); on the Windows PC those two
tests fail with "tar path argument outside cache root" (a path problem in the local executor, the same family as #249),
while the `verify` commands above pass.

---

## 6. Code generation (deterministic, no model)

**What it is.** A `contracts.yaml` lists the interface of a program: which functions each module exports, in which
registers the arguments go, the structs and constants. From that file alone Barthelona generates, with ordinary code and
no model (`src/barthelona/contracts/codegen.py`):

- `gen/<module>.inc`: the include file of a module (its exports and the imports it declared);
- `gen/stubs/<module>.asm`: a skeleton in which every exported function just traps (`ud2`), so an empty project already assembles and links;
- `gen/contracts.h`: C prototypes and struct offsets, for the V5 tests;
- `gen/harness/<test>.c`: one small C program per test that calls a function with the given inputs and exits 1 on a mismatch.

**Why.** Models and people must not change interfaces or tests while code is written (invariants 3 and 4): the
interface is generated from one source, and the **tamper gate** regenerates `gen/` on every check and fails if a file is
missing, edited or extra. That is what made `verify` fail with "`gen/contracts.h` is missing" before the `gen/` folders
of the two test projects were committed.

**How to use it.** It is not a switch: `verify --contracts contracts.yaml` runs the tamper gate, so the project needs its
`gen/`. There is no command yet that writes `gen/`; the function is `barthelona.contracts.codegen.render_all(registry, tests)`,
which returns the file names and texts, and the committed `gen/` folders of `tests/projects/*` were written with it.
A `gen` command and the `header_gen` step of the engine (which also writes `Makefile` and the repository files) are open
work. The single-module create flow does not use contracts yet.

---

## 6a. Create your own program

Today a program is one NASM file (x86-64 Linux, `nasm -f elf64`). You describe it in a text file, Barthelona writes it,
the oracles decide whether it is valid. You write no assembly.

1. Write the task as plain text, the way you would brief a colleague: what the program does, the platform (Linux
   x86-64, raw syscalls, no libc), the exact output and the exit code. Copy `demos/hello/task.txt` as a start into a
   new folder, `demos/myprog/task.txt`. Keep it a prompt a person could write.
2. Run it from the repository root, as one line (the output goes to your folder):

   ```powershell
   python -m barthelona chunked run @demos/myprog/task.txt --profile meterless --assemble --repair 2 --expect-stdout "<the exact output>\n" --expect-exit 0 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/myprog/myprog.asm
   ```

   `--repair-role planner` lets a deeper model repair; `--plan-role planner` plans first; `--facts-sql "SELECT ..."`
   gives the first chunk rows from Zetaris. For a longer program use the create flow (section 2.7).
3. Read the result: `assemble: pass` means NASM accepted the file (with the expectations, it also ran correctly in the
   emulator). On `assemble: fail` read the errors and `myprog.asm.raw.txt`, sharpen the task, run again.
4. Statistics: `python -m barthelona chunked stats`. Run the program yourself only after reading it, on Linux or in
   WSL: `nasm -f elf64 x.asm -o x.o && ld x.o -o x && ./x; echo $?`. The product never runs generated code on the host.

## 6b. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `meterless status` says `unauthorized` | wrong or missing `METERLESS_RUNTIME_TOKEN`; the shell must have loaded `.env` |
| `assemble: unavailable` | NASM not found: set `BARTHELONA_NASM` to `nasm.exe` |
| A chunk fell through to `local_main` | the Meterless route failed (the error is printed); LM Studio answered instead |
| Lane timeout or "provider refused the key" | NVIDIA key rejected or unreachable; re-enter it in Nightshift |
| Empty or truncated answers from a Nemotron model | the output budget ran out while it was thinking; raise `--chunk-tokens` |
| Red "no lane has duty Judge or Verify" in Nightshift | add a second chat lane and set Verify on it |
| `stop_reason=green` but `assemble: fail` | `green` is the chunk loop's own marker; the `assemble:` line is the verdict |

More symptoms: [runbook.md](runbook.md) section 8.

---

## 7. What does not work yet

| Feature | State |
| --- | --- |
| Several modules in one project, the architect, contracts, the sprint planner and loop | not built (Phase 1) |
| AI-composed sprint graphs (L0 templates, L1/L2) | not built (Phase 1/2) |
| Intake, spec, test author, code generation and gates G1 and G4 for **one module** | works (create flow) |
| Streamlit UI | walking skeleton (section 2.8) |
| Gates G0, G2, G3, G5, G6 | not built |
| V3 and V4 as ladder levels | libraries exist; Phase 2 |
| Anthropic, OpenAI, Gemini backends; DeepSeek and DashScope mapping | not built (#252) |
| Training-data collection from runs | storage exists; not connected (section 4) |
| Edit mode for existing projects | Phase 3 |
| FASM, Win64, ELF32, other dialects and presets | Phase 4 |
| Policy Lab, web research, OpenTelemetry | Phase 5 |
| C family, web and 2D | Phase 6 |
| A longer interactive program (a 12-question quiz) from the create flow | does not work yet (the test author wrote wrong expected results; see the hackathon guide) |

---

## 8. Environment requirements

| Component | Windows | Linux |
| --- | --- | --- |
| Python | 3.13 (conda env `barthelona`) | 3.13 (conda) |
| Docker | inside WSL2 Ubuntu 26.04 | native Docker |
| NASM | for `chunked run --assemble` and `check` on the host: on PATH, or `BARTHELONA_NASM` | same |
| Meterless Nightshift | `http://127.0.0.1:8088/v1` (needed for the `meterless` profile) | same |
| Zetaris | `http://localhost:8888/api/v1.0` (needed for facts) | same |
| LM Studio | optional last fallback, `http://127.0.0.1:1234/v1` | same or remote |
| Qdrant | optional, `docker/qdrant/compose.yaml` | same |

If you run a local model next to WSL, cap WSL's memory in `%UserProfile%\.wslconfig` (`[wsl2]` with `memory=8GB`, then
`wsl --shutdown`); without a local model this is not needed. More in [runbook.md](runbook.md).

---

## 9. Directory layout

```
barthelona/
├── config/            models.yaml (catalog, roles, chains), toolchains.lock.json (written by probe)
├── demos/             one folder per demo (a new generated project goes in a new folder here)
├── docker/            toolchain and runner images, Qdrant compose file
├── engines/           world-model/ (TypeScript World Model, not used by the pipeline yet)
├── knowledge/zetaris/ the CSV facts and how to register them in Zetaris
├── src/barthelona/
│   ├── cli/           all commands
│   ├── domain/        the data models
│   ├── engine/        the worker's run graph, spec, test author, code generation
│   ├── llm/           gateway, catalog, Meterless, Zetaris, Markovian, H-MEM
│   ├── contracts/     contracts, code generation, tamper gate
│   ├── verification/  the ladder
│   ├── toolchains/    NASM and GAS adapters, probe
│   ├── emulator/      V3 and V4 libraries and the emulator runner
│   ├── executors/     how commands reach the containers
│   ├── persistence/   the SQLite store
│   ├── scaffold/      repository files of `runs package`
│   ├── training/      training-data writer and reader
│   ├── bench/         the benchmark library
│   └── ui/            the Streamlit pages
├── tests/             unit tests, tests/projects (the two verification projects)
├── var/               not in git: app.sqlite, runs/, hmem.sqlite, training/ ...
└── workspaces/        not in git: one folder per run
```

---

## 10. Next steps

1. Read [`docs/hackathon-demo-guide.md`](hackathon-demo-guide.md) ("Where it stands") and [`docs/create-flow.md`](create-flow.md).
2. Run the commands of sections 2.1, 2.2, 2.4 and 2.5 to see each layer answer.
3. Run the create flow on a one-sentence request (section 2.7) or the UI (section 2.8).
4. The design is in [`docs/architecture.md`](architecture.md); the plan in [`docs/roadmap.md`](roadmap.md).

_Last updated: 2026-10-24._
