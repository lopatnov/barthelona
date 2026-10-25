# Barthelona at the Open Agent Hackathon 2026: demo guide

How to set up the three hackathon layers on your machine and what Barthelona can honestly show today. Read
"Where it stands" first: it says what was run live, what was not proven and what does not exist yet. Words you
do not know (oracle, gate, route, chunk, H-MEM, lane, file table ...) are explained in the [Glossary](#glossary).

Last updated 2026-10-24, from live runs on the owner's PC (free NVIDIA Nemotron through Meterless Nightshift, a
local Zetaris, the worker and the Unicorn emulator).

---

## Table of contents

1. [Where it stands](#where-it-stands)
2. [The three layers](#the-three-layers)
3. [Prerequisites](#prerequisites)
4. [Layer 1: Zetaris](#layer-1-data-zetaris)
5. [Layer 2: Barthelona](#layer-2-build-barthelona)
6. [Layer 3: Meterless and Nemotron](#layer-3-power-meterless-and-nemotron)
7. [Check that the layers work together](#check-that-the-layers-work-together)
8. [Demos](#demos)
9. [Hackathon form: what we integrated and where](#hackathon-form-what-we-integrated-and-where)
10. [Troubleshooting](#troubleshooting)
11. [Glossary](#glossary)

---

## Where it stands

Rules of this hackathon run: free models only (NVIDIA Nemotron through Nightshift), no paid model APIs and no
local models. Zetaris and Meterless are both required. Everything a demo shows is produced by Barthelona; no
person hand-writes a demo's sources, tests, README, CI or release files.

**Worked live (2026-10-24):**

- The create flow through the worker: `runs submit`, gate G1, code generation, NASM, the Unicorn emulator and gate
  G4 reached `green` for "print hello" (twice) and "print the digits 1 to 9" (twice). Each run took 4 model calls and
  about a minute of model time, with no repair attempts.
- `runs package` turned a green run into 7 files (source, golden tests, README with the request and per-model
  calls, tokens and seconds, CI, release workflow, dependabot). `check` on the packaged source passed in the
  emulator.
- Zetaris: two knowledge tables (37 Linux x86-64 syscalls, 11 ABI rows) are registered in the owner's local
  Zetaris, read into the spec and test-author prompts, mined into 48 H-MEM facts by `zetaris seed`, and recalled in
  every chunk. `zetaris publish` copies run and memory data back into Zetaris tables.
- Meterless: the `meterless` profile calls Nightshift; the `meterless/auto` and `meterless/deep` routes both
  answered. Which concrete model serves a route is decided by Nightshift's lanes: check the run details there
  (every run records `answered by`). All runs above were answered by Nemotron; on the evening of 2026-10-24 a Llama
  model was also added to the Race lane, so read `answered by` before saying which model answered.
- The gateway repeats a call that failed with a temporary error (Nightshift answers an intermittent
  `404 provider_error`), up to twice, with jitter.

**Not proven:**

- **Compounding** (the same task run twice on the same memory, the second run needing fewer chunks). The hello and
  digits tasks fit in one chunk, so a second run cannot need fewer. An earlier hello run (2026-10-23) took 9 chunks
  and the next one chunk, but that second output did not assemble, so it does not count. FizzBuzz, the task long
  enough to need several chunks, has not passed on any profile yet (#246).
- **The temperament questionnaire** (the English demo). The first run stopped at gate G1 because 3 of its 8 golden
  tests had wrong expected results (#259). A fix to the test author is on the branch; the rerun is pending.
- **A published demo.** The packaged English "digits" project is on the owner's PC only. No GitHub CI or release
  has run on it yet.

**Does not exist yet:** several modules in one project, the architect, contracts and sprint loop, GAS and other
dialects, editing an existing project, a `cloud` profile that can answer (#252), and a reference model that checks
the author's expected test results (#259).

---

## The three layers

| Layer | Technology | Role in Barthelona |
| --- | --- | --- |
| **DATA** | Zetaris | Structured facts (Linux syscalls, ABI rules) read into the prompts, recalled as H-MEM facts, and run history published back as tables |
| **BUILD** | Barthelona's worker and Markovian engine | Runs a request through spec, tests, code generation, NASM and the emulator; long tasks in bounded chunks with H-MEM recall in every chunk |
| **POWER** | Meterless Nightshift with free NVIDIA Nemotron | The `meterless` profile: routes `meterless/auto` (main and worker) and `meterless/deep` (planning, review) |

All layers run on your machine. The project was built with Claude Code; any editor works, and nothing in the demos
needs Cursor.

### A run in one picture

What happens to one request in the create flow, and which technology does each step (unknown words are in the
[Glossary](#glossary)):

```
request (one sentence)
  |
  v intake       language, goal in English, key entities        model: meterless/auto
  v spec         requirements and modules                       model: meterless/deep + Zetaris facts
  v test author  golden tests, one per requirement              model: meterless/deep + Zetaris facts
  v G1 gate      a PERSON reads and approves spec and tests     (frozen afterwards)
  v code         bounded chunks, H-MEM recall, Zetaris facts    model: meterless/auto
  v oracles      NASM assembles; the emulator runs the golden tests;
  |              a rejection goes back to the model with the reason (repairs on meterless/deep, up to 2)
  v G4 gate      a PERSON reads and approves the code
  v green        main.asm saved, memory written; `runs package` writes the repository
```

Each model call is routed by Nightshift to a Nemotron model and recorded (model, tokens, seconds); Zetaris is read
for the prompts and can be written afterwards (`zetaris publish`). Nothing a model says is accepted without the
oracles.

---

## Prerequisites

These are what the tested machine had (checked 2026-10-24), not vendor minimums; for Zetaris's own requirements see
the participant guide and https://github.com/zetaris/getting-started.

| Requirement | Tested with | Notes |
| --- | --- | --- |
| OS | Windows 11 with WSL2 | Linux is the reference host for the engine; macOS is untested |
| RAM | 16 GB | Docker was given 8 GB for Zetaris |
| Disk | 15 GB free | Zetaris images are large |
| Docker | Docker Desktop | Zetaris, and the `bart-tc` toolchain container |
| NASM | any recent | `nasm` on PATH, or `BARTHELONA_NASM` |

> **Start Zetaris first.** The first start downloads large images (30 to 45 minutes). Set up the other layers while it
> runs.

---

## Layer 1: DATA, Zetaris

### 1.1 Install and start

Follow the hackathon participant guide (`.reference/7e1b7ca3995b4673b30a73555c87e71f.pdf`) and
https://github.com/zetaris/getting-started: download the platform bundle from Zetaris Cloud ("Run locally"), run the
registry sign-in command it gives you, then `docker compose up -d` in the getting-started folder. Give Docker at
least 8 GB of memory and 4 CPUs. Full details are in [zetaris-guide.md](zetaris-guide.md).

On the tested machine the web UI is on http://localhost:3000, the REST API on http://localhost:8888/api/v1.0 and JDBC
on port 10000.

### 1.2 API key and environment

Create an API key in the Zetaris web UI. It is shown once. Set it for your shell (never commit it):

```powershell
setx ZETARIS_API_KEY "<key>"        # Windows; open a new terminal afterwards
```

```bash
export ZETARIS_API_KEY="<key>"      # Linux, macOS, WSL
```

`ZETARIS_REST_URL` (default `http://localhost:8888/api/v1.0`) and `ZETARIS_ORG_ID` (default `1`) only need setting
when yours differ. Check it:

```
python -m barthelona zetaris status        # online, unauthorized, offline or unconfigured
python -m barthelona zetaris sql "SHOW LIGHTNING DATABASES"
```

### 1.3 Register the knowledge tables

Barthelona ships the facts as CSV files in `knowledge/zetaris/` (`linux_x64_syscalls.csv`, `abi_facts.csv`). Zetaris
creates the tables from files with `CREATE LIGHTNING FILESTORE TABLE`; there is no `INSERT` path. The exact docker
and SQL steps, verified on the hackathon stack, are in [`knowledge/zetaris/README.md`](../knowledge/zetaris/README.md).
The numbers were written from memory of the public kernel table and the System V ABI and still need a documentation
check before anything depends on them.

Check the result:

```
python -m barthelona zetaris sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name IN ('write', 'exit_group')"
```

### 1.4 Seed memory and publish run data

```
python -m barthelona zetaris seed --memory var/hmem.sqlite
python -m barthelona zetaris publish <driver container>
```

`seed` turns the registered tables into H-MEM facts (source `zetaris:<table>`); `publish` copies run history and
memory into Zetaris tables so they can be queried with SQL. See [zetaris-engines.md](zetaris-engines.md).

**Done with DATA when** `zetaris status` prints `online` and the `SELECT` above returns rows.

---

## Layer 2: BUILD, Barthelona

### 2.1 Environment

```powershell
.\scripts\create_env.ps1          # once
. .\scripts\activate.ps1          # your own terminal: this loads .env
.\scripts\doctor.ps1
```

```bash
scripts/create_env.sh
source scripts/activate.sh
scripts/doctor.sh
```

Coding agents never run `activate`; they use `.\scripts\dev.ps1 [-LoadEnv] <command>` (see
[create-flow.md](create-flow.md)).

### 2.2 Check the core

```
python -m barthelona version
scripts/setup-toolchain.sh        # builds the bart-tc container (WSL on Windows)
python -m barthelona probe
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm --contracts tests/projects/nasm-triple/contracts.yaml --tests tests/projects/nasm-triple/tests.yaml --require "V0,V1,V2,V5,V6"
```

The create flow needs only NASM and the Unicorn emulator, not the container. The container is for the verification
ladder above V2.

### 2.3 The engines

The Markovian chunk loop (`src/barthelona/llm/markovian.py`) and H-MEM (`src/barthelona/llm/hmem.py`) are Python
ports of the Meterless engine specs; what is and is not ported is listed in [hackathon-demo.md](hackathon-demo.md).

**Done with BUILD when** `verify` passes on `nasm-triple` and `check` passes on a packaged project (Demo A).

---

## Layer 3: POWER, Meterless and Nemotron

### 3.1 Nightshift

1. Install Nightshift from https://meterless.ai and start it. It serves an OpenAI-compatible API on
   http://127.0.0.1:8088/v1 by default.
2. **Setup, Providers, add NVIDIA**, with a free key from https://build.nvidia.com/. The key stays in Nightshift. It
   is also fine to keep `NVIDIA_API_KEY` in your own `.env`, but Barthelona never reads it.
3. **NIGHT, LANES**: add at least two lanes backed by different free models. The hackathon participant guide says a
   model never grades its own answers, so Nightshift warns when two lanes share one family (source: the participant
   guide, https://meterless.ai; the warning itself was not re-checked in the UI on 2026-10-24). Nemotron 3.5 needs
   thinking switched off on the main lane (`chat_template_kwargs: {enable_thinking: false}`); the deep lane keeps
   thinking on. This was observed in live runs on 2026-10-23 (PRs #204 and #208, and the comment in
   `config/models.yaml`); model details are on https://build.nvidia.com/.
4. Copy the runtime token from **Console** into `METERLESS_RUNTIME_TOKEN` (same way as the Zetaris key).
   `METERLESS_BASE_URL` is only needed when the URL is not the default.

```
python -m barthelona meterless status      # online and the meterless/* routes
```

### 3.2 What the catalog does

`config/models.yaml` has three Meterless routes: `meterless_auto` (roles `main` and `worker`), `meterless_deep`
(`planner`, `escalation`) and `meterless_fast` (`cheap`). Every chain ends with the local model `local_main` in the
shipped catalog. Under the free-models rule use a copy of the catalog with the LM Studio provider disabled and pass
it with `--catalog` (`worker`, `chunked run`). Make the copy by copying `config/models.yaml` and setting `enabled: false`
on the `lmstudio` provider (the file used in the live runs was `var/proof/models-free.yaml`, kept on that PC and
not in git). Then a run whose Nightshift calls all fail ends as
`no_model_available` instead of calling a local model.

### 3.3 Local fallback

The default catalog, `config/models.yaml`, ends every role chain of the `meterless` profile with `local_main`
(for example `worker: [meterless_auto, local_main]`), so when Nightshift fails a call falls through to a local model
if one is running. To have one: install LM Studio, load a coder model with a 16K context, start the local server on
port 1234. On Windows cap WSL memory in `%UserProfile%\.wslconfig` (`memory=8GB`) and run `wsl --shutdown`.

The hackathon runs used a private copy of the catalog (`var/proof/models-free.yaml`) with the local model switched
off, to keep the promise of free models only: with it a failed call stops the run instead of falling back. That copy
is not in the repository; the committed catalog keeps the fallback.

**Done with POWER when** `meterless status` prints `online`.

---

## Check that the layers work together

```
python -m barthelona zetaris status          # online
python -m barthelona meterless status        # online
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm --contracts tests/projects/nasm-triple/contracts.yaml --tests tests/projects/nasm-triple/tests.yaml --require "V0,V1,V2,V5,V6"
python -m barthelona worker --once --trace-reasoning var/proof/reasoning.md   # in a second terminal: processes what Demo A queues
```

---

## Demos

### Demo A: create a program through the worker (works)

The path that was run live. Terminal 1 keeps the worker running; terminal 2 queues and answers gates.

```
python -m barthelona worker --catalog var/proof/models-free.yaml --trace-reasoning var/proof/reasoning.md
python -m barthelona runs submit "Write a NASM program that prints the digits 1 to 9, one per line, and exits 0"
python -m barthelona runs status                  # the run id, and the open gate
python -m barthelona runs decide <run_id> approve # G1: read the spec and tests first
python -m barthelona runs decide <run_id> approve # G4: the verdict and the program
python -m barthelona runs package <run_id> --out var/proof/digits-pkg --barthelona-ref <full commit sha>
python -m barthelona check var/proof/digits-pkg/src/digits.asm --tests var/proof/digits-pkg/tests/golden.json
```

At G1, recompute the expected results of the tests from the specification before you approve: the tests are frozen
afterwards, and the test author has written wrong expected results once (#259). `--trace-reasoning` writes what each
model thought and answered to a file. All flags: [create-flow.md](create-flow.md).

What it shows: spec and tests from a model, an oracle (NASM and the emulator) deciding, two human gates, and a
packaged project with README, CI and release workflow, all generated. The `meterless/auto` and `meterless/deep`
calls, their tokens and seconds are in the packaged README.

### Demo B: Zetaris facts in the prompts (works)

With `ZETARIS_API_KEY` set the worker reads both knowledge tables into the spec and test-author prompts by default
(`worker --facts-sql "SELECT ..."` replaces the statement). The facts reach the model as an untrusted-data block, and
the oracle still decides. To show it, run Demo A with a task that names a syscall and look in `--trace-reasoning`
for the syscall number the model used. With the default statement a down Zetaris gives a run without facts, not a
failed run; with an explicit `--facts-sql` a failing Zetaris stops the run as `infra_error`.

`chunked run` accepts `--facts-sql` too:

```
python -m barthelona chunked run "NASM program that prints Hello using sys_write" --profile meterless --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'" --assemble --repair 2 --expect-stdout "Hello\n" --expect-exit 0 --out var/proof/zeta.asm --trace-reasoning var/proof/zeta-reasoning.md --stats var/runs.sqlite
```

### Demo C: memory and long tasks (not proven yet)

The pieces exist: H-MEM recall in every chunk, write-back after an assembled run, `chunked stats` and the
`runs`/`run_chunks` tables published to Zetaris. The claim "the second run needs fewer chunks" has no valid
evidence yet (see "Where it stands"). To test it honestly you need a task that takes several chunks, such as
FizzBuzz (`demos/fizzbuzz/`), run twice against the same `--memory` file, with the second run counting only if it also
assembles and passes the emulator check. If both runs finish in one chunk, say that the task was too short.

### What to say, and what not to say

| Demo | Evidence you can show | Do not claim |
| --- | --- | --- |
| A, create flow | Green run, package, `check` pass, per-model table | That the result is ABI-checked, fuzzed or multi-module |
| B, Zetaris | Facts in the prompt and in the reasoning log, `seed` and `publish` tables | That the tables are verified against the kernel source |
| C, memory | The mechanism and the published tables | That a second run is cheaper: not shown |

---

## Hackathon form: what we integrated and where

Answers for the submission form, each with the place in the repository where a reviewer can check it.

### Which Meterless features are integrated

| Feature | Integrated? | What it does here | Where |
| --- | --- | --- | --- |
| **Nightshift runtime** | Yes | Every model call of the `meterless` profile (the default) goes to Nightshift's OpenAI-compatible API. Routes `meterless/auto`, `deep` and `fast` are mapped to roles; each call records which model answered | Provider, models and role chains: `config/models.yaml` (`providers.meterless`, `meterless_auto`, `meterless_deep`, `meterless_fast`, profile `meterless`). Client and discovery: `src/barthelona/llm/meterless.py`, `src/barthelona/llm/openai_chat.py`. Probe: `python -m barthelona meterless status` (`src/barthelona/cli/meterless.py`) |
| **H-MEM** (persistent memory) | Yes | A Python port of the memory spec. Before every chunk the best memories are recalled; after the assembler and emulator accept a program the lesson is written back; the knowledge tables seed it | `src/barthelona/llm/hmem.py`; recall in each code-generation chunk: `src/barthelona/engine/codegen.py`; seeding from Zetaris: `src/barthelona/llm/zetaris_memory.py` (`zetaris seed`) |
| **Markovian Thinking** (context optimisation) | Yes | Long work runs in bounded chunks that carry a short summary instead of the whole history; the run prints the measured saving against a full history (single-chunk runs print "too short to compare") | `src/barthelona/llm/markovian.py`; used by `python -m barthelona chunked run` (`src/barthelona/cli/chunked.py`) and by code generation in the worker (`src/barthelona/engine/codegen.py`) |
| **World Model** (state and provenance) | **No, still working on integration** | Event-sourced shared state for agents running in parallel, written in TypeScript. Nothing in the pipeline uses it yet and the official conformance runner has not been run against it | `engines/world-model/index.ts`, status in `engines/world-model/README.md` |
| AI Hotspot | No | Not used | |

If the form has "Still working on integration", tick it and name the World Model there.

### What kinds of intelligence Nightshift powers

**Language and reasoning only:** chat, analysis and coding. In the create flow the models read the request (intake), write the specification and the golden tests (`deep` route), write the NASM program in chunks (`auto` route) and repair it from the assembler's and emulator's reports. Code: `src/barthelona/engine/spec.py`, `tests_author.py`, `codegen.py`. No vision, image, audio, video or 3D call exists in the project. Vision, image generation and 3D appear only as possible later uses for the 2D and 3D demos (roadmap Phase 6).

### What goes well with Zetaris

A local Zetaris runs next to the engine. Two knowledge tables (37 Linux x86-64 system calls and 11 ABI rules) are registered as file tables and read over the REST API into the spec and test-author prompts; they seed H-MEM; and run history is written back as tables (`barthelona_runtime`) that can be queried with SQL. All of it was checked end to end on the owner's PC.

Where: the REST client `src/barthelona/llm/zetaris.py` (`zetaris status`, `zetaris sql`, read-only), facts in prompts `worker --facts-sql` and `chunked run --facts-sql`, seeding `src/barthelona/llm/zetaris_memory.py`, publishing `src/barthelona/llm/zetaris_publish.py` (`zetaris publish`), the data in `knowledge/zetaris/*.csv`, and the table registration in [`zetaris-guide.md`](zetaris-guide.md) and [`zetaris-engines.md`](zetaris-engines.md).

### What does not go well with Zetaris

Getting our own data in was manual: files had to be copied into the container's shared volume and registered with `CREATE LIGHTNING FILESTORE TABLE`, and we found no documented way to insert rows over REST. The knowledge is only two small tables (no assembler manuals loaded yet), and the Zetaris event is never emitted by the engine (#256). No run has yet shown that the facts make code better or cheaper to produce.

---

## Troubleshooting

### Zetaris

| Symptom | Fix |
| --- | --- |
| `unauthorized` | Create a new key in the Zetaris UI and update `ZETARIS_API_KEY`; open a new terminal after `setx` |
| `offline` | `docker compose up -d` in the getting-started folder; check Docker's memory |
| `unconfigured` | `ZETARIS_API_KEY` is not set in this shell |
| A query returns no rows | The table is not registered or is in another database: see `knowledge/zetaris/README.md` |

### Meterless and Nightshift

| Symptom | Fix |
| --- | --- |
| `unauthorized` | Copy a fresh runtime token from the Nightshift Console into `METERLESS_RUNTIME_TOKEN` |
| `offline` | Start Nightshift; check the port (default 8088) |
| `404 provider_error` | Intermittent upstream error; the gateway repeats the call up to twice. If it persists, check the lane in Nightshift |
| Empty or cut-off reply | The thinking lane used the output budget; use the non-thinking lane for long outputs, or raise `--chunk-tokens` |
| The run used `local_main` | A Nightshift call failed and the chain fell through; with the free-models catalog it stops instead |

### Barthelona

| Symptom | Fix |
| --- | --- |
| `assemble: unavailable` | Install NASM or set `BARTHELONA_NASM` |
| A run stops as `max_attempts` | The checker rejected every attempt or the model gave no valid JSON twice; read `runs status <run_id>` |
| The run stops as `budget_time` | The run's `--wall-s` limit ran out while generating code |
| `runs package` refuses | The run is not green, the project has several modules, or the files exist (`--force`) |

### Windows

| Issue | Fix |
| --- | --- |
| `conda activate` does nothing | Use `. .\scripts\activate.ps1` (note the leading dot) |
| `wsl -l` output is garbled | Set `WSL_UTF8=1` (`activate` does) |
| Python not found in Git Bash | Use `scripts/dev.sh python ...` |

---

## Glossary

Words are grouped by what they belong to, then in the order you meet them. If a word is missing, tell us: this page
is meant to be readable without knowing assemblers, SQL or agent frameworks.

### The product and a run

| Term | Meaning |
| --- | --- |
| **Barthelona** | The system in this repository: it turns a request in plain language into a small assembly program and checks it with real tools |
| **Request** | The sentence or text a person writes, for example "print the digits 1 to 9". The only human-written input of a demo |
| **Run** | One request going through the whole pipeline. It has a **run id** (`run-20261024-...`), a status and files in `var/runs/<run id>/` |
| **Spec** | The specification the system writes from the request: requirements, the program's modules, constraints. A person approves it at gate G1 |
| **Golden test** | A test that says: for this input the program must print exactly this and exit with this code. The system writes them at the same time as the spec |
| **Gate (G1, G4)** | A point where a person approves or rejects. **G1**: the spec and the golden tests (they are frozen afterwards). **G4**: the finished program. Answer with `runs decide <run id> approve` or in the UI's Approvals page |
| **Green** | The only success: the oracles accepted the program and the person approved G4 |
| **Stop reason** | Why a run ended; every run has one. See the table below |
| **Worker** | The process (`python -m barthelona worker`) that takes queued runs and drives them to the next gate. The UI and the `runs` commands only queue runs and answer gates |
| **Package** | `runs package`: writes the repository of a green run (source, tests, README, CI, release workflow) into a folder |
| **Project folder** | The name under `demos/` that receives the packaged repository (`--project NAME`, or the New Request page) |
| **Demo** | A folder under `demos/`. A real demo is produced by Barthelona from a prompt, never written by hand (see AGENTS.md); several folders there are placeholders |
| **Preset, dialect** | Which assembler and target: `linux-x64-nasm-static` means NASM syntax, Linux, x86-64, no C library. Dialects: `nasm`, `gas-intel`, `gas-att` |
| **Single module** | One source file. The create flow handles only this today; several modules need the sprint planner, which does not exist yet |

**Stop reasons.**

| Stop reason | Plain meaning |
| --- | --- |
| `green` | Done and accepted |
| `max_attempts` | The model gave unusable answers, or the oracles rejected every attempt including the repairs |
| `no_model_available` | No model in the chain could answer (all failed or were skipped) |
| `human_abort` | A person rejected a gate or cancelled the run |
| `unsupported_target` | The chosen preset is not supported by the pipeline yet |
| `infra_error` | A required service failed (for example Zetaris when `--facts-sql` was given) |
| `refusal` | A model refused the request |
| `budget_tokens`, `budget_time`, `budget_cost`, `max_sprints` | A limit was reached; every run is bounded |

### Checking the result (the oracles)

| Term | Meaning |
| --- | --- |
| **Oracle** | A tool that decides whether code is acceptable: assembler, linker, emulator, tests. Models propose, oracles decide; a model's review is advice only |
| **Assembler (NASM, GAS)** | Turns assembly text such as `mov rax, 1` into machine code. NASM and the GNU assembler (`as`, "GAS") are the two supported |
| **Linker (`ld`)** | Joins machine code of several files into one program and finds the entry point |
| **Symbol** | A name in a program, such as a function (`_start`). The symbol check compares the names found in the machine code with the contract |
| **`_start`** | The entry point of a program without the C library: where execution begins. It must end by calling the exit syscall |
| **Syscall** | A request from a program to the Linux kernel: `write` (number 1) prints, `exit` (60) ends the program |
| **ABI** | The agreement on how functions pass arguments (which registers), keep registers and use the stack. Breaking it works in a test and crashes elsewhere |
| **Emulator (Unicorn)** | A virtual CPU. The program runs inside it, never on your PC, and its output and exit code are compared with the golden test |
| **Ladder (V0 to V8)** | The ordered checks: V0 syntax, V1 assemble and symbols, V2 link, V3 static ABI lint, V4 dynamic ABI checks, V5 C-harness tests, V6 whole-program golden input and output. V3 and V4 are libraries, V7 and V8 are planned |
| **Contracts (`contracts.yaml`)** | The declared interface of a program: functions, argument registers, structs. The single source of truth for interfaces |
| **`gen/` and the tamper gate** | `gen/` holds files generated from the contracts (include files, stubs, C headers, test harnesses). The tamper gate regenerates them on every check and fails if one is missing, edited or extra, so nobody changes interfaces while code is written |
| **Toolchain, lock file** | The set of tools (`nasm`, `as`, `ld`, `gcc`, `gdb`, `make`) in the `bart-tc` container; `probe` writes their exact versions to `config/toolchains.lock.json` |
| **`bart-tc`, `bart-run`** | The two Docker containers: `bart-tc` has the tools, `bart-run` is a sandbox that runs test programs |

### Models: Meterless, Nightshift, Nemotron

| Term | Meaning |
| --- | --- |
| **Meterless** | The company and open-source project behind Nightshift and the H-MEM, Markovian and World Model specifications |
| **Nightshift** | The Meterless program on your PC that serves an OpenAI-compatible API (`http://127.0.0.1:8088/v1`) and routes each request to a model; it may let several models try the same request |
| **NVIDIA Nemotron** | The free model family reached through Nightshift in the hackathon runs. Which model really answered is recorded as `answered by` |
| **Route** (`meterless/auto`, `deep`, `fast`) | What Barthelona asks Nightshift for: `auto` the general choice, `deep` the strongest reasoning, `fast` the quickest. Nightshift picks the model |
| **Lane** | A model with a duty (Race, Judge, Verify) inside Nightshift's own screens. Barthelona does not name lanes; it asks for routes |
| **Race** | Several models try the same request and one answer wins. It is inside Nightshift: it does not split a project among agents |
| **Gateway, backend** | The Barthelona code that sends a request to the models of a chain. The one backend today speaks the OpenAI chat protocol |
| **Profile** | A named set of chains in `config/models.yaml`: `meterless`, `local-only`, `hybrid`, `cloud` (only `meterless` and `local-only` can answer today) |
| **Role, chain** | A role (`main`, `worker`, `planner`, `cheap`, `escalation`) names a job; its chain is the ordered list of models to try. Every chain ends with the local model |
| **Fall-through** | When a chain entry cannot be used or fails, the gateway tries the next one and shows why (`chunk 1 fell through: ...`) |
| **Local model (`local_main`)** | The model in LM Studio on your PC. It is the last entry of every chain; demo runs under the free-models rule disable it |
| **Token** | The unit models count text in (about four characters). Limits and costs are in tokens |
| **Reasoning, `<think>`** | Some models write their thinking before the answer. It is stripped before the code is extracted; `--trace-reasoning` logs it |

### Memory and long tasks

| Term | Meaning |
| --- | --- |
| **Markovian engine** | Produces a long answer as bounded **chunks** so the prompt does not grow with the answer; this repository has its own Python port of the Meterless specification |
| **Chunk, carry-over** | One bounded generation step; a short state (the carry-over) is passed to the next chunk. A chunk ends with the marker `[STATE_CHECKPOINT]` (more to come) or `[TASK_COMPLETE]` (done) |
| **`peak_prompt`, `standard_cost`, `markovian_cost`, `efficiency`** | Summary numbers: the largest prompt sent; the input tokens a full-history run would have used; the input tokens chunking used; the saving in percent. `too short to compare` for a single chunk |
| **H-MEM** | Hierarchical memory (a Python port of the Meterless specification): facts recalled before each chunk and written after a green run, in a SQLite file (`--memory`) |
| **Recall, seed** | Recall: facts chosen for this task are put into the prompt. Seed: `zetaris seed` turns the Zetaris tables into memory entries (48 facts) |
| **World Model** | A TypeScript engine for shared, event-sourced state between agents (`engines/world-model/`). Built, but not used by the pipeline yet |

### Data: Zetaris

| Term | Meaning |
| --- | --- |
| **Zetaris** | A data platform you query with SQL. Here it holds the assembler facts and receives published run history |
| **Lightning database, file table** | Zetaris's way to expose files as tables: `CREATE LIGHTNING DATABASE`, then `CREATE LIGHTNING FILESTORE TABLE` over a CSV in the containers' shared volume |
| **`barthelona_files`, `barthelona_runtime`** | The two databases: `barthelona_files` has `linux_x64_syscalls` (37 rows) and `abi_facts` (11 rows); `barthelona_runtime` has runs, chunks, memories and the memory ledger after `zetaris publish` |
| **Facts** | Rows from those tables placed in the spec and test-author prompts and in the first chunk (`--facts-sql`), marked as untrusted data |
| **Untrusted data, injection guard** | Text from outside (Zetaris rows, recalled memory) is wrapped in a block the model is told not to obey, and is refused if it looks like an instruction to the model |
| **API key** | Created in the Zetaris UI; read from `ZETARIS_API_KEY`, never committed |

### Commands and files you will see

| Term | Meaning |
| --- | --- |
| **`dev.ps1`, `-LoadEnv`** | A wrapper that runs one command with the conda environment; `-LoadEnv` also exports the keys from `.env` for that one command |
| **Catalog (`config/models.yaml`)** | Providers, models, roles, chains and profiles. A copy with `lmstudio` disabled is how a run is kept from using a local model (`--catalog`) |
| **`var/`** | Runtime data, not in git: `app.sqlite` (runs, events, gates), `runs/<run id>/` (spec, tests, code), `hmem.sqlite`, `runs.sqlite` |
| **`assemble: pass`** | The line `chunked run` prints when NASM assembled the program and, with `--expect-stdout`, the emulator saw the expected output |

---

## Hackathon day checklist

- [ ] Zetaris up, `zetaris status` prints `online`, both knowledge tables return rows
- [ ] `zetaris seed` done (48 facts) and `zetaris publish` has run once
- [ ] Nightshift up with two lanes on different free models, `meterless status` prints `online`
- [ ] A catalog copy with LM Studio disabled, if you promise free models only
- [ ] NASM found (`python -m barthelona check` on a packaged project passes)
- [ ] Demo A rehearsed once; you know which models served `auto` and `deep` (Nightshift run details)
- [ ] **Agent activity is logged (required by the hackathon):** `worker` and `chunked run` write the reasoning log to `var/activity.md` by default (`--trace-reasoning FILE` picks another file, `off` disables it), and `chunked run` also needs `--stats var/runs.sqlite`; after a run, the file exists and `python -m barthelona chunked stats --db var/runs.sqlite` or the `llm_calls` query shows the calls ([how](current-status.md))
- [ ] You can state what is not proven (compounding, temperament, published demo)

---

## Resources

| Resource | Link |
| --- | --- |
| Create flow: commands and flags | [`create-flow.md`](create-flow.md) |
| Architecture | [`architecture.md`](architecture.md) |
| Meterless guide | [`meterless-guide.md`](meterless-guide.md) |
| Zetaris guide and engines | [`zetaris-guide.md`](zetaris-guide.md), [`zetaris-engines.md`](zetaris-engines.md) |
| Current status | [`current-status.md`](current-status.md) |
| Runbook | [`runbook.md`](runbook.md) |
| Hackathon participant guide | `.reference/7e1b7ca3995b4673b30a73555c87e71f.pdf` |
| Meterless on GitHub | https://github.com/Meterless/Meterless |
| Zetaris getting started | https://github.com/zetaris/getting-started |
| NVIDIA build | https://build.nvidia.com/ |
