# Barthelona Hackathon 2026 Demo Guide

Complete step-by-step instructions for demonstrating Barthelona's technologies at the Open Agent Hackathon 2026.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites Check](#prerequisites-check)
3. [Layer 1: DATA — Zetaris Setup](#layer-1-data--zetaris-setup)
4. [Layer 2: BUILD — Cursor + Barthelona Setup](#layer-2-build--cursor--barthelona-setup)
5. [Layer 3: POWER — Meterless/NVIDIA Nemotron Setup](#layer-3-power--meterlessnvidia-nemotron-setup)
6. [Integration Verification](#integration-verification)
7. [Demo Scenarios](#demo-scenarios)
8. [Running the Demos](#running-the-demos)
9. [Troubleshooting](#troubleshooting)
10. [Glossary](#glossary)

---

## Overview

This guide prepares you to demonstrate **Barthelona** — a local-first agentic system whose goal is to create or edit multi-file assembly projects from natural-language requests (today it builds single-module programs; see "Status today") — using the three hackathon layers:

| Layer     | Technology                             | Role in Barthelona                                                                                                                          |
| --------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **DATA**  | Zetaris                                | Structured knowledge store: syscall and ABI fact tables read by SQL, used in the prompts (and via `--facts-sql`), seeding H-MEM, receiving run data |
| **BUILD** | Cursor + Barthelona                    | Development environment; Barthelona's create flow and `chunked run` with its own Markovian and H-MEM ports (bounded chunks, memory)          |
| **POWER** | Meterless Nightshift + NVIDIA Nemotron | Model provider: Barthelona asks for `meterless/auto`, `deep` or `fast` and Nightshift routes to Nemotron lanes (a local fallback exists but is off for demo runs) |

**Eligibility**: All three layers must be running on your machine.

---

## Status today (2026-10-24, checked on the Windows dev PC)

Read this first: the rest of the guide is a setup walkthrough, and this table says what has actually been shown to work.

| Piece                       | State                                                                                                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Zetaris (DATA)              | Running locally; `zetaris status` prints `online`. Two knowledge tables are registered (`barthelona_files.linux_x64_syscalls`, 37 rows; `barthelona_files.abi_facts`, 11 rows). Their rows go into the spec and test-author prompts by default, seed H-MEM (`zetaris seed`), and run data is written back with `zetaris publish` (`barthelona_runtime.*`). |
| Meterless + Nemotron (POWER) | Nightshift answers on `http://127.0.0.1:8088/v1`; `meterless status` prints `online`. In the runs below every call was answered by `nvidia/nemotron-3-ultra-550b-a55b` through `meterless/auto`, `meterless/deep` and `meterless/fast`.                                   |
| Create flow (BUILD)         | **In open PR #253, not merged into `main` yet:** `worker` plus `runs submit / status / decide / package` for **single-module** programs. On that branch "print hello" and "print the digits 1 to 9" each went green end to end on Nemotron only (request, spec, tests, gate G1, code, gate G4), and `runs package` wrote source, tests, README and CI/release workflows. On `main` today the worker stops at gate G1 and there is no `runs` command. |
| Not working yet             | An interactive 12-question questionnaire: the test author wrote wrong expected results (3 of 8 tests) and the run was parked at gate G1. FizzBuzz through `chunked run` failed the oracle in every setup tried (local models, `local-coder`, Nightshift). Multi-module sprints, the full Streamlit UI and generated docs/release for multi-module projects do not exist yet (`docs/current-status.md` section 7). |
| Memory proof                | Not demonstrated. The hello task needs one chunk, so a second run cannot need fewer. In the measured digits runs the second run recalled more context but needed the same number of calls and more tokens. Do not claim fewer chunks unless a run shows it.                |
| Models                      | Decision for the hackathon period: free models only, that is Nemotron through Nightshift. No local model and no paid cloud model is used for demo runs.                                                                                                                      |

What the runs looked like (UTC, from the run database; times include waiting for a person to approve the gates): hello 3.7 minutes with 4 model calls, about 1.6 minutes of model work; digits 2.4 to 2.5 minutes with 4 calls. A first attempt can fail when the provider behind Nightshift answers `404 Function ... Not found` for a moment (3 of the first 4 hello attempts did); issue #255 and PR #253 add a bounded retry on the same model, and the runs that followed on that branch needed none.

---

## Prerequisites Check

Before starting, ensure your machine meets requirements:

| Requirement | Minimum                     | Recommended                      |
| ----------- | --------------------------- | -------------------------------- |
| **OS**      | Windows 11 / macOS / Linux  | Windows 11 (tested)              |
| **RAM**     | 16 GB                       | 32 GB (for local fallback model) |
| **Disk**    | 15 GB free                  | 50 GB free                       |
| **Docker**  | 25+                         | Latest                           |
| **WSL2**    | Ubuntu 26.04 (Windows only) | Ubuntu 26.04                     |
| **GPU**     | Optional (cloud models)     | NVIDIA for local models          |

> ⚠️ **Start Zetaris first** — it downloads large container images (30–45 min). Set up Build and Power while it runs.

---

## Layer 1: DATA — Zetaris Setup

### 1.1 Register at Zetaris Cloud

1. Go to Zetaris Cloud → **Run locally** page
2. Download the **Zetaris platform bundle**
3. Copy the **registry sign-in command** (looks like `docker login registry.zetaris.com -u ... -p ...`)

### 1.2 Install Prerequisites

```bash
# Docker Desktop (if not installed)
# https://docs.docker.com/get-docker

# Git (if not installed)
# https://git-scm.com/downloads

# WSL2 Ubuntu 26.04 (Windows only)
wsl --install -d Ubuntu
# Then: wsl -d Ubuntu -e sudo apt update && sudo apt upgrade -y
```

### 1.3 Configure Docker Resources

**Docker Desktop → Settings → Resources → Advanced:**

- **Memory**: 8 GB (minimum) — Zetaris needs this
- **CPUs**: 4
- **Disk**: 15+ GB free

### 1.4 Install Zetaris

Follow the installation guide that comes with the Zetaris bundle (in the `getting-started` repository:
`docs/install/updated_zetaris_installation_guide.md`; the sign-in command and the compose file come from Zetaris Cloud
"Run locally"). The commands in the first version of this guide (a `docker login registry.zetaris.com ...` line, a
`/health` check) were not verified and have been removed; `GET /api/v1.0/health` answers 404 on the dev PC.

What the dev PC runs after the bundle is up (checked with `docker ps`, 2026-10-24):

| Container          | Image (hackathon build `2.4.3`)             | Port on this PC               |
| ------------------ | ------------------------------------------- | ----------------------------- |
| `zetaris-api-1`    | `zetarishackathon.azurecr.io/zetaris-ndp-api`    | `127.0.0.1:8888` (REST API)   |
| `zetaris-driver-1` | `zetarishackathon.azurecr.io/zetaris-ndp-driver` | `127.0.0.1:4040` and others   |
| `zetaris-ui-1`     | `zetarishackathon.azurecr.io/zetaris-new-ui`     | `0.0.0.0:3000` (web UI)       |
| `zetaris-postgres-1` | `postgres:16-alpine`                      | `127.0.0.1:32772`             |

The web UI is on port **3000**, the REST API on **8888** (the first version of this guide said 8888 for the UI).

### 1.5 Create API Key

1. Open the Zetaris web UI: http://localhost:3000
2. Log in with the account from the bundle.
3. Create the API key in the UI (the Zetaris getting-started guide says to create it there yourself; never ask an
   agent to create it). The exact menu path was not re-checked.
4. Copy the key — you won't see it again. Put it in `.env` as `ZETARIS_API_KEY` (see 1.6).

### 1.6 Test Zetaris Connection

Put `ZETARIS_API_KEY` in `.env` (and `ZETARIS_REST_URL`, `ZETARIS_ORG_ID` only if they differ from
`http://localhost:8888/api/v1.0` and `1`). Agent shells and scripts that must see `.env` use the `-LoadEnv` switch
(`.\scripts\dev.ps1 -LoadEnv <command>`, D-057); in your own activated terminal `.env` is already loaded.

```bash
python -m barthelona zetaris status
# → online http://localhost:8888/api/v1.0
python -m barthelona zetaris sql "SHOW LIGHTNING DATABASES"
# → one row per Lightning database (name | description | id)
```

The status command sends `POST <rest url>/sql-editor/sqls/run` with `Authorization: Bearer <key>`, `X-Org-ID`,
`X-Request-ID` and a body with `queryId`, `sql`, `source` and `limit`, and expects `SELECT 1` to return `1`. The
`unconfigured`, `unauthorized` and `offline` answers are described in Troubleshooting.

### 1.7 Register the Assembler Facts (once)

The knowledge lives in two CSV files in `knowledge/zetaris/` (`linux_x64_syscalls.csv`, 37 rows, and
`abi_facts.csv`, 11 rows). They become Zetaris **file tables**; the first version of this guide created tables with
`CREATE TABLE ... INSERT`, which was never run and is not how Zetaris registers files. The verified steps (2026-10-24)
are in [`knowledge/zetaris/README.md`](../knowledge/zetaris/README.md); in short:

1. Copy both CSVs into the volume that the Zetaris api and driver containers share, from the `knowledge/zetaris`
   folder with **relative** paths (an absolute `C:\...` path makes `docker cp` read `C` as a container name):

   ```bash
   docker exec <driver container> mkdir -p /home/zetaris/customer-data/shared/barthelona
   docker cp ./linux_x64_syscalls.csv <driver container>:/home/zetaris/customer-data/shared/barthelona/linux_x64_syscalls.csv
   docker cp ./abi_facts.csv <driver container>:/home/zetaris/customer-data/shared/barthelona/abi_facts.csv
   ```

2. Send these statements one at a time (the Zetaris SQL editor, or `POST /sql-editor/sqls/run`; the API key was
   accepted for `CREATE`). A second run answers "already exists":

   ```sql
   CREATE LIGHTNING DATABASE barthelona_files DESCRIBE BY "Barthelona knowledge tables";
   CREATE LIGHTNING FILESTORE TABLE linux_x64_syscalls FROM barthelona_files FORMAT CSV
     OPTIONS (path "/home/zetaris/customer-data/shared/barthelona/linux_x64_syscalls.csv", header "true", delimiter ",");
   CREATE LIGHTNING FILESTORE TABLE abi_facts FROM barthelona_files FORMAT CSV
     OPTIONS (path "/home/zetaris/customer-data/shared/barthelona/abi_facts.csv", header "true", delimiter ",");
   ```

`python -m barthelona zetaris sql` itself is read-only (one `SELECT`, `SHOW`, `DESCRIBE` or `WITH`), so it cannot run
these statements. `zetaris publish` is the only command that writes: it registers and fills the
`barthelona_runtime` tables (`runs`, `run_chunks`, `memories`, `memory_ledger`) from the local SQLite files.
The numbers in the CSVs were written from memory of the public syscall table and still need the check against the
kernel table and the psABI that `knowledge/zetaris/README.md` asks for.

### 1.8 Verify Facts Are Queryable

```bash
python -m barthelona zetaris sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name IN ('write','exit_group')"
# → write | rdi=fd | rsi=buf | rdx=count
# → exit_group | rdi=status | None | None
```

**✅ You're done with DATA when:** `python -m barthelona zetaris status` prints `online` and that query returns the two rows.

---

## Layer 2: BUILD — Cursor + Barthelona Setup

### 2.1 Install Cursor

1. Download from https://cursor.com
2. Install and sign in (Cursor credit pays for Grok/Composer during development)
3. Open the Barthelona repository in Cursor:
   ```bash
   cursor c:/projects/barthelona-parallel-dev
   ```

### 2.2 Set Up Barthelona Environment

```bash
# Windows PowerShell
.\scripts\create_env.ps1
. .\scripts\activate.ps1
.\scripts\doctor.ps1

# Git Bash / Linux
scripts/create_env.sh
source scripts/activate.sh
scripts/doctor.sh
```

### 2.3 Verify Core Barthelona CLI

```bash
# Version and schemas
python -m barthelona version
python -m barthelona schema

# Probe toolchains (needs Docker + bart-tc container)
scripts/setup-toolchain.sh  # or: wsl -d Ubuntu -e bash scripts/setup-toolchain.sh
python -m barthelona probe

# Verify ladder on test projects
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm \
  --contracts tests/projects/nasm-triple/contracts.yaml \
  --tests tests/projects/nasm-triple/tests.yaml
```

### 2.4 The Meterless engines (Markovian, H-MEM)

There is nothing to install. Barthelona carries its **own Python ports** of the Markovian and H-MEM specs
(Apache-2.0, github.com/Meterless/Meterless), not the Meterless code: `src/barthelona/llm/markovian.py`
(`run_markovian`, `MarkovianConfig`) and `src/barthelona/llm/hmem.py` (`HMem`). Check that they import:

```bash
python -c "from barthelona.llm.markovian import run_markovian; print('Markovian OK')"
python -c "from barthelona.llm.hmem import HMem; print('H-MEM OK')"
```

(An earlier version of this guide imported `MarkovianEngine` and `HMemStore`; those names do not exist.)

### 2.5 Explore the Prompts

The benchmark prompt templates are in `bench/prompts/` (`single.md.j2`, `fix.md.j2`, `c.md.j2`). The prompts of the
create flow (intake, spec, test author) are in `src/barthelona/engine/` for now; the planned
`policies/v1/prompts/` folder does not exist yet.

### 2.6 Cursor Integration Tips

- **Grok**: Use for harder, longer coding tasks (Ctrl+K → Grok)
- **Composer**: Fast everyday coding (default)
- **Barthelona CLI**: Run from Cursor's integrated terminal (Ctrl+`)
- **Debug**: Set breakpoints in `src/barthelona/cli/verify.py` etc.

**✅ You're done with BUILD when:** `python -m barthelona verify` passes on `nasm-triple` and `gas-triple` test projects.

---

## Layer 3: POWER — Meterless/NVIDIA Nemotron Setup

### 3.1 Option A: Meterless Nightshift (Recommended)

#### 3.1.1 Install Nightshift

1. Download from https://meterless.ai
2. Install and launch the app
3. Verify it's running: http://127.0.0.1:8088/v1/models

#### 3.1.2 Add NVIDIA Provider

1. **Nightshift UI → Setup → Providers → Add Provider → NVIDIA**
2. Get free API key from https://build.nvidia.com/
3. Paste key in Nightshift (stays there, never in `.env`)
4. Click **Save**

#### 3.1.3 Lanes

Barthelona only talks to the three routing modes `meterless/auto`, `meterless/deep` and `meterless/fast`
(`config/models.yaml`: roles `main`/`worker` use `auto`, `planner` uses `deep`, `cheap` uses `fast`); which model a
mode picks is decided by the lanes in Nightshift (NIGHT, LANES; the lanes have a duty such as Race, Judge or Verify,
and the dev PC uses a Race lane). The model ids in the first version of this guide (`nemotron-3.5-lightning-30b-a3b`,
`gpt-4o-mini`) were copied from the setup text and **not re-checked**; follow Nightshift's own screens. What is
verified: with the lanes the dev PC had on 2026-10-24 (before a Llama model was added to the Race lane that evening),
every call of the free-only runs (all three modes) was answered by `nvidia/nemotron-3-ultra-550b-a55b`, as shown in
`chunked stats` (`answered by`) and in the `llm_calls` table of `var/app.sqlite`. With more than one model in a lane,
read `answered by` after each run instead of assuming the model.

> The hackathon setup text says a model should not grade its own answers and that Nightshift shows a red warning with a
> single lane family; keep two different model families in the lanes if you need that warning gone. Barthelona's
> reviewer is advisory only (the assembler and the emulator decide).

#### 3.1.4 Get Runtime Token

1. **Nightshift → Console → Runtime Token → Copy**
2. Add to `.env` (create from `.env.example`):

```bash
# .env (gitignored — NEVER commit!)
METERLESS_RUNTIME_TOKEN=your-token-here
# METERLESS_BASE_URL=http://127.0.0.1:8088/v1  # optional if default
```

#### 3.1.5 Verify Meterless Connection

```bash
python -m barthelona meterless status
# Expected: "online" + lists meterless/auto, meterless/deep, meterless/fast
```

### 3.2 Direct NVIDIA API

Not available. `config/models.yaml` has no `nvidia` provider and no backend for one (the first version of this guide
showed a YAML block for it; it was never tested). Reach Nemotron through Nightshift.

### 3.3 Local Fallback Model (LM Studio) — optional, off for demo runs

Decision of 2026-10-24: for the hackathon period only Nemotron through Nightshift is used for demo runs; no local model
and no paid cloud model. Be aware that **every model chain in `config/models.yaml` ends in the local model** (invariant
11), so with LM Studio running a failed Nightshift call falls through to `local_main` without a warning. That is how
a run on the `cloud` profile ended up answered by a local model on 2026-10-24. To make a run fail instead, give it a
catalog copy in which only the `lmstudio` provider has `enabled: false`:

```bash
python -m barthelona chunked run ... --profile meterless --catalog var/proof/models-free.yaml
python -m barthelona worker --catalog var/proof/models-free.yaml ...
```

(`var/proof/` is a gitignored scratch folder; copy `config/models.yaml` there and change that one line. Do not edit the
committed catalog for this.) If you do want a local fallback: install LM Studio (https://lmstudio.ai), load a coding
model with a 16K context, start the local server (port 1234) and check http://127.0.0.1:1234/v1/models.

### 3.4 WSL Memory Cap (Windows only, only if you run a local model next to WSL)

Create `%UserProfile%\.wslconfig`:

```ini
[general]
instanceIdleTimeout=-1  # never stop distro when idle

[wsl2]
memory=8GB              # leave RAM for LM Studio on Windows
processors=8
```

Then: `wsl --shutdown`

**✅ You're done with POWER when:** `python -m barthelona meterless status` prints `online` and lists the `meterless/*` routes. A local fallback is optional (3.3).

---

## Integration Verification

Run the complete smoke test to verify all three layers work together:

```bash
# 1. Activate environment
. .\scripts\activate.ps1  # or: source scripts/activate.sh

# 2. Verify Zetaris
python -m barthelona zetaris status
# → online

# 3. Verify Meterless
python -m barthelona meterless status
# → online + routes listed

# 4. Verify Barthelona core
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm \
  --contracts tests/projects/nasm-triple/contracts.yaml \
  --tests tests/projects/nasm-triple/tests.yaml
# → All levels V0-V2, V5, V6: PASS

# 5. Zetaris facts reach the models: read the knowledge tables
python -m barthelona zetaris sql "SELECT name, arg1 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'"
# → write | rdi=fd

# 6. Seed a fresh H-MEM store from Zetaris and look at what recall returns
python -m barthelona zetaris seed --memory var/proof/hm.sqlite
# → seeded 48 new facts; H-MEM now holds 48   (a second run says 0 new facts)

# 7. One run through Nightshift: hello world with memory and stats
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/proof/hmem.sqlite --stats var/proof/runs.sqlite \
  --out var/proof/hello.asm
# → look for "assemble: pass" and the per-chunk table (answered by: the Nemotron model)

# 8. Show stats
python -m barthelona chunked stats --db var/proof/runs.sqlite
```

Step 7 passed with local models on 2026-10-24 (hello in one chunk, `assemble: pass`); an earlier live Nightshift run
of the same task is recorded in `docs/hackathon-demo.md` (2026-10-23). It was not repeated through Nightshift on
2026-10-24; the Nightshift-only evidence of that day comes from the create flow (Demo 1 below, open PR #253).

**✅ All layers integrated when:** steps 2 to 6 pass and step 7 prints `assemble: pass`.

---

## Demo Scenarios

Three demo scenarios, in the order of how well they are backed by evidence. Each says what was actually shown.

### Demo 1: The create flow, request to green (hello, digits)

**Needs open PR #253** (it adds `runs submit / status / decide / package` and the code and G4 steps; on `main` the
worker stops at gate G1). Evidence from 2026-10-24: "hello" and "digits 1 to 9" went green on Nemotron only, each in
about 4 model calls and 1 to 2 minutes of model work.

```powershell
# Terminal 1: the worker (state in a scratch folder; catalog copy with lmstudio disabled, see 3.3)
.\scripts\dev.ps1 -LoadEnv python -m barthelona worker --catalog var/proof/models-free.yaml `
  --db var/proof/e2e/app.sqlite --checkpoints var/proof/e2e/cp.sqlite --runs var/proof/e2e/runs `
  --memory var/proof/e2e/hm.sqlite --poll 1

# Terminal 2: submit, then answer the two gates
.\scripts\dev.ps1 python -m barthelona runs submit "Write a program that prints hello and a newline, then exits with code 0." `
  --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs        # prints the run id
.\scripts\dev.ps1 python -m barthelona runs status <run id> --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs
# at gate ...-G1: read runs/<run id>/spec.json and tests.json, then
.\scripts\dev.ps1 python -m barthelona runs decide <run id> approve --db var/proof/e2e/app.sqlite
# at gate ...-G4: read runs/<run id>/main.asm, then approve the same way; the run ends `green`
.\scripts\dev.ps1 python -m barthelona runs package <run id> --out var/proof/hello-pkg `
  --barthelona-ref <full commit sha> --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs
```

`runs decide` takes only `--db` (no `--runs`). Seed the memory first with `python -m barthelona zetaris seed --memory
var/proof/e2e/hm.sqlite` if you want the Zetaris facts in it.

**Key talking points (true as measured):**

- "A person writes one sentence; the system writes the spec and the tests, and a person approves them at gate G1."
- "The assembler and the emulator decide; the model only proposes. The reviewer is advisory."
- "Every call is recorded (model, tokens, latency) in `var/app.sqlite`; here all of them were Nemotron."
- "`runs package` writes the repository: source, tests, README, CI and a release workflow."

**Do not say:** that it builds multi-module programs or an interactive quiz (it does not yet), or that the release was
published (the packaged workflows were not run on GitHub).

### Demo 2: Multi-chunk generation (FizzBuzz) — currently failing, show only as an honest limit

**What it shows:** Markovian chunking and the repair loop on a task that does not fit one chunk.

```bash
python -m barthelona chunked run @demos/fizzbuzz/task.txt \
  --profile meterless --catalog var/proof/models-free.yaml \
  --plan-role planner --review-role cheap --repair-role planner \
  --chunk-tokens 2000 --carryover-tokens 128 --max-chunks 8 --assemble --repair 2 \
  --expect-stdout "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz\n" --expect-exit 0 \
  --memory var/proof/fb-hmem.sqlite --stats var/proof/fb-runs.sqlite --out var/proof/fizzbuzz.asm
```

Result on 2026-10-24: it did not pass in any setup tried. With local models the programs were wrong or the run
crashed; through Nightshift two runs failed the oracle (a leaked reasoning text and a state block ended up in the
`.asm`, issue #254, fixed in PR #253). The Markovian numbers are real (for example 8 chunks, `efficiency` about 75%
against a full history, by the project's own cost model), but there is no green FizzBuzz to show.

### Demo 3: Zetaris fact injection

**What it shows:** facts from a structured store are put in front of the model, and the oracles still decide.

```bash
python -m barthelona chunked run "Write a NASM program that prints 'Hello' using the write syscall" \
  --profile meterless \
  --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name IN ('write','exit_group')" \
  --assemble --repair 2 --expect-stdout "Hello\n" --expect-exit 0 \
  --memory var/proof/hmem.sqlite --stats var/proof/runs.sqlite --out var/proof/zeta-hello.asm
```

**Key talking points (true as measured):**

- "The syscall facts live in Zetaris tables (37 syscalls, 11 ABI facts) and come back as rows."
- "They are untrusted data: wrapped in a `[ZETARIS FACTS]` block, with the injection guard in front."
- "In the create flow they are used by default (spec and test-author prompts) and seed H-MEM (`zetaris seed`)."
- "Run data goes back into Zetaris (`zetaris publish` → `barthelona_runtime.*`), so it can be queried with SQL."

This exact command with `--facts-sql` against the real tables was not re-run on 2026-10-24; the default facts of the
create flow and `zetaris seed` / `publish` were.

---

## Running the Demos

Run the demos from the repository root. A suggested order for a live session (about 15 minutes; model calls on
Nemotron take 5 to 60 seconds each):

1. Show the layers: `python -m barthelona zetaris status`, `python -m barthelona meterless status`,
   `python -m barthelona zetaris sql "SELECT name, arg1 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'"`.
2. Demo 1, the create flow (needs PR #253): submit one sentence, read the spec and tests at G1, approve, read the code
   at G4, approve, then `runs package`.
3. Demo 3, Zetaris: `zetaris seed` into a fresh memory file, the recall output, and `zetaris publish` followed by
   `SELECT COUNT(*) FROM barthelona_runtime.runs` (`publish` needs the id of the Zetaris driver container and
   `--hmem-db <file>`).
4. Say plainly where the limits are (Demo 2 and the "Not working yet" row at the top).

There is no all-in-one script: the first version of this guide had a `demo.ps1` that ran the "memory proof" twice;
that proof is not demonstrated (see Status today), so the script was removed.

### What Judges Can See

| Demo                | What is shown                                                                                    | Evidence                                              |
| ------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| Create flow         | One sentence becomes spec, tests, code and a package; two gates answered by a person              | Run ends `green`; `llm_calls` rows; the packaged repo |
| Zetaris             | Syscall and ABI facts come from SQL tables and flow into the prompts and into H-MEM               | `zetaris sql`, `zetaris seed`, recall output          |
| Meterless/Nemotron  | Every model call was answered by Nemotron through `meterless/auto`, `deep` and `fast`            | `answered by` in `chunked stats`; `llm_calls`         |
| Markovian numbers   | `peak_prompt`, `standard_cost`, `markovian_cost`, `efficiency` per run (the project's cost model) | The summary line of `chunked run`                     |
| Limits, stated      | FizzBuzz not green; the quiz needs a better test author; no memory-proof run yet                   | The "Not working yet" row                             |

---

## Troubleshooting

### Zetaris Issues

| Symptom               | Fix                                                                   |
| --------------------- | --------------------------------------------------------------------- |
| `unauthorized`        | Regenerate API key in the Zetaris UI (port 3000); update `ZETARIS_API_KEY` |
| `offline`             | Start the Zetaris stack from the bundle; check `docker ps` and Docker resources |
| `unconfigured`        | The key is not in this process: for an agent shell use `dev.ps1 -LoadEnv`; otherwise set `ZETARIS_API_KEY` and restart the shell (a Windows `setx` only reaches new processes) |
| Query returns no rows or "table not found" | Tables are `barthelona_files.linux_x64_syscalls` and `barthelona_files.abi_facts`; register them as in 1.7; `barthelona_runtime.*` exists only after `zetaris publish` |
| `zetaris publish` fails with `WinError 2` | On Windows `docker` may be only `docker.bat` (`wsl docker %*`); issue #248, fixed in PR #253 (the command now starts docker by its full path) |

### Meterless/Nightshift Issues

| Symptom                | Fix                                                     |
| ---------------------- | ------------------------------------------------------- |
| `unauthorized`         | Copy a fresh token from the Nightshift Console; update `.env` (an agent shell needs `-LoadEnv`, or a restart after `setx`) |
| `offline`              | Start the Nightshift app; check port 8088               |
| Red "no Judge lane" in Nightshift | Per the hackathon setup text, add a lane on a different model family (not re-checked) |
| Falls to `local_main`  | Every chain ends in the local model; use a catalog copy with `lmstudio` disabled (3.3) to see the real error |
| `no_model_available` right after the first calls | Look for `404 Function ... Not found` in the provider error: an upstream blip that PR #253 retries (#255); resubmit |
| Empty/truncated output | Increase `--chunk-tokens` (default 8000); PR #253 names a reply cut off at the output limit (#257) |
| Reasoning text or `[STATE_CHECKPOINT]` inside the `.asm` | Issue #254, fixed in PR #253; the raw answer is in `<out>.raw.txt` |

### Barthelona Issues

| Symptom                  | Fix                                                                   |
| ------------------------ | --------------------------------------------------------------------- |
| `assemble: unavailable`  | Install NASM (https://www.nasm.us/) or set `BARTHELONA_NASM`          |
| `assemble: fail`         | Read NASM errors; sharpen task; re-run                                |
| Docker container missing | `scripts/setup-toolchain.sh` (or WSL equivalent)                      |
| `chunks=` not decreasing | Not a bug: a short task needs one chunk, and recall adds context without reducing calls (measured on the digits runs). Memory is written only after `assemble: pass` |
| `runs decide ... --runs` fails | `runs decide` takes only `--db` |

### Windows-Specific

| Issue                         | Fix                                               |
| ----------------------------- | ------------------------------------------------- |
| `conda activate` does nothing | Use `. .\scripts\activate.ps1` (note leading dot) |
| `wsl -l` garbled              | `WSL_UTF8=1` (activate script sets this)          |
| Python not found in Git Bash  | Use `scripts/dev.sh python` or activated terminal |

---

## Glossary

| Term                      | Meaning                                                           |
| ------------------------- | ----------------------------------------------------------------- |
| **Agent**                 | App where AI model decides steps/tools to finish a task           |
| **API Key/Token**         | Secret password for service auth; keep in `.env`                  |
| **Base URL**              | Web address for model requests (e.g., `http://127.0.0.1:8088/v1`) |
| **Chunk**                 | Bounded generation unit (default 8K tokens) in Markovian Engine   |
| **H-MEM**                 | Hierarchical Memory — recalls facts from prior successful runs    |
| **Lane**                  | A model served by Nightshift; Barthelona asks for a mode (`meterless/auto`, `deep`, `fast`) and Nightshift picks the lane |
| **Markovian Engine**      | Long generation as bounded chunks with flat context               |
| **Oracle**                | Tool that decides correctness (NASM, linker, emulator)            |
| **Gate (G1, G4)**         | A point where a person approves: G1 the spec and tests, G4 the code |
| **Run id / `runs`**       | The create flow's unit of work; `runs submit/status/decide/package` (PR #253) |
| **Zetaris**               | Data virtualization platform; SQL interface for structured facts  |
| **`--facts-sql`**         | CLI flag injecting Zetaris query results into chunk 1             |
| **`assemble: pass/fail`** | NASM verdict — the true oracle                                    |

---

## Quick Reference Card

```bash
# ===== ONE-TIME SETUP =====
# 1. Zetaris: install the bundle (the getting-started install guide), create the API key in the UI (http://localhost:3000)
#    then register the knowledge tables (section 1.7)
# 2. Barthelona
.\scripts\create_env.ps1 ; . .\scripts\activate.ps1
scripts/setup-toolchain.sh        # Windows: wsl -d Ubuntu -e bash scripts/setup-toolchain.sh
python -m barthelona probe
# 3. Nightshift: install from meterless.ai, add the NVIDIA provider and lanes in its screens
#    copy the runtime token into .env as METERLESS_RUNTIME_TOKEN
# 4. Secrets in an agent shell: prefix commands with  .\scripts\dev.ps1 -LoadEnv   (in your own activated terminal .env is loaded)

# ===== DAILY START =====
python -m barthelona zetaris status    # online
python -m barthelona meterless status  # online + meterless/* routes

# ===== DEMO COMMANDS =====
# Zetaris facts and memory
python -m barthelona zetaris sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'"
python -m barthelona zetaris seed --memory var/proof/hm.sqlite        # 48 facts, a second run adds 0

# Create flow (open PR #253): worker in one terminal, then in another
python -m barthelona runs submit "Write a program that prints hello and a newline, then exits with code 0." --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs
python -m barthelona runs status <run id> --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs
python -m barthelona runs decide <run id> approve --db var/proof/e2e/app.sqlite      # at G1 and again at G4
python -m barthelona runs package <run id> --out var/proof/hello-pkg --barthelona-ref <full sha> --db var/proof/e2e/app.sqlite --runs var/proof/e2e/runs

# Long task as chunks (one command; see the demos/ READMEs for the full flags)
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 --memory var/proof/hmem.sqlite --stats var/proof/runs.sqlite --out var/proof/hello.asm
python -m barthelona chunked stats --db var/proof/runs.sqlite
```

---

## Hackathon Day Checklist

- [ ] Zetaris running (`docker ps` shows the api, driver, ui and postgres containers `healthy`)
- [ ] `ZETARIS_API_KEY` reaches the shell (`-LoadEnv` or a fresh terminal), `zetaris status` → `online`
- [ ] Knowledge tables registered: the `write` / `exit_group` query in 1.8 returns two rows
- [ ] Nightshift running, `meterless status` → `online` and the `meterless/*` routes
- [ ] Demo runs use a catalog copy with `lmstudio` disabled (3.3) so no local model answers by accident
- [ ] Barthelona env works, `.\scripts\doctor.ps1` passes
- [ ] Open PR #253 merged (or its branch checked out) if you show the create flow
- [ ] One create-flow run rehearsed end to end (about 4 minutes with the gates)
- [ ] The limits are on the slide: FizzBuzz and the quiz are not green; no memory-proof run
- [ ] `smoke_test.py` passes (if provided by the hackathon)

---

## Resources

| Resource                    | Link                                              |
| --------------------------- | ------------------------------------------------- |
| Barthelona Architecture     | [`docs/architecture.md`](architecture.md)         |
| Meterless Guide             | [`docs/meterless-guide.md`](meterless-guide.md)   |
| Zetaris Guide               | [`docs/zetaris-guide.md`](zetaris-guide.md)       |
| Quickstart                  | [`docs/quickstart.md`](quickstart.md)             |
| Current Status              | [`docs/current-status.md`](current-status.md)     |
| Runbook                     | [`docs/runbook.md`](runbook.md)                   |
| Hackathon Participant Guide | `.reference/7e1b7ca3995b4673b30a73555c87e71f.pdf` |
| Meterless GitHub            | https://github.com/Meterless/Meterless            |
| Zetaris Getting Started     | https://github.com/zetaris/getting-started        |
| NVIDIA Nemotron             | https://build.nvidia.com/                         |

---

_Last updated: 2026-10-24. Based on Open Agent Hackathon 2026 Participant Setup Guide (21 Oct 2026)._
