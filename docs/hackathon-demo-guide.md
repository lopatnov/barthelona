# Barthelona at the Open Agent Hackathon 2026: demo guide

How to set up the three hackathon layers on your machine and what Barthelona can honestly show today. Read
"Where it stands" first: it says what was run live, what was not proven and what does not exist yet.

Last updated 2026-10-24, from live runs on the owner's PC (free NVIDIA Nemotron through Meterless Nightshift, a
local Zetaris, the worker and the Unicorn emulator).

---

## Table of contents

1. [Where it stands](#where-it-stands)
2. [The three layers](#the-three-layers)
3. [Prerequisites](#prerequisites)
4. [Layer 1: Zetaris](#layer-1-data--zetaris)
5. [Layer 2: Barthelona](#layer-2-build--barthelona)
6. [Layer 3: Meterless and Nemotron](#layer-3-power--meterless-and-nemotron)
7. [Check that the layers work together](#check-that-the-layers-work-together)
8. [Demos](#demos)
9. [Troubleshooting](#troubleshooting)
10. [Glossary](#glossary)

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
  answered. Which concrete model serves a route is decided by Nightshift's lanes: check the run details there.
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

---

## Prerequisites

| Requirement | Minimum | Notes |
| --- | --- | --- |
| OS | Windows 11, macOS or Linux | Tested on Windows 11 with WSL2 |
| RAM | 16 GB | Zetaris needs about 8 GB for Docker |
| Disk | 15 GB free | Zetaris images are large |
| Docker | 25+ | Zetaris, and the `bart-tc` toolchain container |
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
python -m barthelona verify tests/projects/nasm-triple --level V6
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
3. **NIGHT, LANES**: add at least two lanes backed by different free models. A model never grades its own answers,
   so Nightshift warns when two lanes share one family. Nemotron 3.5 needs thinking switched off on the main lane
   (`chat_template_kwargs: {enable_thinking: false}`); the deep lane keeps thinking on.
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

### 3.3 Optional: a local fallback

Not used in the hackathon runs. If you want one: install LM Studio, load a coder model with a 16K context, start the
local server on port 1234. On Windows cap WSL memory in `%UserProfile%\.wslconfig` (`memory=8GB`) and run
`wsl --shutdown`.

**Done with POWER when** `meterless status` prints `online`.

---

## Check that the layers work together

```
python -m barthelona zetaris status          # online
python -m barthelona meterless status        # online
python -m barthelona verify tests/projects/nasm-triple --level V6
python -m barthelona worker --once           # in a second terminal: processes what Demo A queues
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
python -m barthelona chunked run "NASM program that prints Hello using sys_write" --profile meterless --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'" --assemble --repair 2 --expect-stdout "Hello\n" --expect-exit 0 --out var/proof/zeta.asm
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

| Term | Meaning |
| --- | --- |
| **Gate (G1, G4)** | A point where a person approves or rejects: G1 the specification and tests, G4 the finished program |
| **Oracle** | A tool that decides correctness: NASM, the linker, the emulator. Models propose, oracles decide |
| **Chunk** | One bounded generation step of the Markovian engine; state is carried between chunks, so the prompt stays flat |
| **H-MEM** | Hierarchical memory: facts recalled before each chunk and written back after an assembled run |
| **Route (`meterless/auto`, `deep`, `fast`)** | A Nightshift routing mode; the lanes in Nightshift decide which concrete model answers |
| **Lane** | A model with a duty in Nightshift (Race, Judge, Verify) |
| **Zetaris** | Data virtualisation platform with a SQL interface; here the store of knowledge tables and published run data |
| **Profile** | A catalog set of role chains: `local-only`, `hybrid`, `cloud`, `meterless` |

---

## Hackathon day checklist

- [ ] Zetaris up, `zetaris status` prints `online`, both knowledge tables return rows
- [ ] `zetaris seed` done (48 facts) and `zetaris publish` has run once
- [ ] Nightshift up with two lanes on different free models, `meterless status` prints `online`
- [ ] A catalog copy with LM Studio disabled, if you promise free models only
- [ ] NASM found (`python -m barthelona check` on a packaged project passes)
- [ ] Demo A rehearsed once; you know which models served `auto` and `deep` (Nightshift run details)
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
