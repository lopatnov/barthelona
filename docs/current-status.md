# Current Status: What Works Today (2026-10-24)

This document describes the **actual, runnable capabilities** of barthelona as of Phase 0. The engine (Meta-Agentic Scrum loop, AI-composed sprint graphs, Streamlit UI) is **only started**: Phase 1a slice 1 is the worker and the first nodes of the outer run graph (section 5). What follows is the deterministic spine: toolchains, verification, model gateway, and CLI tools that work **without any LLM**.

> **Integration guides:** [`docs/meterless-guide.md`](meterless-guide.md) | [`docs/zetaris-guide.md`](zetaris-guide.md) | [`docs/hackathon-demo-guide.md`](hackathon-demo-guide.md)

---

## 1. Quick Start (Windows PowerShell)

```powershell
.\scripts\create_env.ps1        # Creates conda env 'barthelona' (Python 3.13) + hash-locked deps
. .\scripts\activate.ps1        # Note the leading dot
.\scripts\doctor.ps1            # Environment health check
copy .env.example .env          # Optional: add cloud API keys
```

Git Bash: `scripts/create_env.sh`, then `source scripts/activate.sh`.

WSL2 Ubuntu 26.04 and Docker are used for building and sandboxed testing. Full setup: [`docs/runbook.md`](runbook.md).

---

## 2. CLI Commands (All Working Today)

Run `python -m barthelona --help` for the full list. Key commands:

| Command             | Purpose                                                        | Status                    |
| ------------------- | -------------------------------------------------------------- | ------------------------- |
| `version`           | Print barthelona version                                       | ✅                        |
| `schema [Document]` | Print JSON schema of a domain document, or list all            | ✅                        |
| `probe`             | Probe `bart-tc` container, write `config/toolchains.lock.json` | ✅ (needs Docker)         |
| `verify`            | Run verification ladder (V0–V2, V5, V6) on assembly sources    | ✅ (needs Docker)         |
| `training status`   | Show opt-in training data setting and sample counts            | ✅                        |
| `meterless status`  | Probe Meterless Runtime (Nightshift)                           | ✅                        |
| `zetaris status`    | Probe Zetaris REST API                                         | ✅                        |
| `zetaris sql`       | Run read-only SQL against Zetaris                              | ✅                        |
| `chunked run`       | Run a long task through the model gateway as Markovian chunks  | ✅ (needs model endpoint) |
| `chunked stats`     | Show run statistics from SQLite DB                             | ✅                        |

### 2.1 `probe` — Toolchain Lock File

```bash
python -m barthelona probe --output config/toolchains.lock.json --transport auto
```

**What it does:**

- Connects to the `bart-tc` Docker container via WSL (Windows) or directly (Linux)
- Runs `--version` for every tool (nasm, yasm, fasm, as, ld, gcc, gdb, make)
- Records the container image digest and each tool's version + path
- Writes `config/toolchains.lock.json` (git-tracked, reproducible)

**Prerequisites:**

- Docker running in WSL (Windows) or on Linux host
- `bart-tc` and `bart-run` images built and `bart-tc` running: one command, `scripts/setup-toolchain.sh` (Windows: `wsl -d Ubuntu -e bash scripts/setup-toolchain.sh`), see `docs/runbook.md` section 2.3

### 2.2 `verify` — Verification Ladder

```bash
python -m barthelona verify <workspace> --level V6 --dialect nasm \
  --contracts contracts.yaml --tests tests.yaml --transport auto
```

**Levels implemented (native-asm family):**
| Level | Check | Where | Status |
|-------|-------|-------|--------|
| V0 | Syntax only (`nasm -o /dev/null`, `as -o /dev/null`) | bart-tc | ✅ |
| V1 | Assemble each module; `nm` symbol check vs registry | bart-tc | ✅ |
| V2 | Link (`ld` or `gcc`); unresolved/duplicate symbols, entry point | bart-tc | ✅ |
| V3 | Static ABI lint (Capstone): GNU-stack, PIE relocations, syscall clobber, red zone | `barthelona.emulator.abi_static` | library done, 100% on the corpus; not yet a ladder level (D-056) |
| V4 | Unicorn dynamic ABI checks: alignment, callee-saved, stack balance, direction flag | `barthelona.emulator.machine` | library done, 100% on the corpus; not yet a ladder level (D-056) |
| V5 | C-harness tests (gcc in bart-tc, run in bart-run) | bart-run | ✅ |
| V6 | Whole-program golden I/O (qemu-user later) | bart-run | ✅ |
| V7 | gdb/qemu trace (after failure, for fixer) | bart-run | ⏳ Phase 2 |
| V8 | Real Windows (Windows Sandbox) | Windows | ⏳ Later |

**Tamper gate (T)** runs after every apply; **Minimality gate (M)** in edit mode. Both are implemented.

**Example — run the NASM triple-module test project:**

```bash
python -m barthelona verify tests/projects/nasm-triple \
  --level V6 --dialect nasm \
  --contracts tests/projects/nasm-triple/contracts.yaml \
  --tests tests/projects/nasm-triple/tests.yaml
```

### 2.3 `meterless status` — Nightshift Runtime Probe

```bash
python -m barthelona meterless status --url http://127.0.0.1:8088/v1
# or set METERLESS_BASE_URL and METERLESS_RUNTIME_TOKEN in .env
```

> **Full guide:** [`docs/meterless-guide.md`](meterless-guide.md) — installation, lane config, profiles, H-MEM, troubleshooting

**What it does:**

- Calls `GET /v1/models` with the `METERLESS_RUNTIME_TOKEN` (Bearer auth)
- Reports state: `online` (meterless/\* models listed), `unauthorized` (401/403), or `offline`
- Lists available `meterless/*` model routes (e.g., `meterless/auto`, `meterless/deep`, `meterless/fast`)

**Configuration in `config/models.yaml`:**

```yaml
providers:
  meterless:
    kind: openai_chat
    base_url: ${METERLESS_BASE_URL:-http://127.0.0.1:8088/v1}
    api_key_env: METERLESS_RUNTIME_TOKEN
    local: false
    network: lan
    enabled: true
    max_concurrency: 2
    structured_output: none
    timeout_s: 180
    headers: { meterless-app: barthelona, meterless-scope: user }

models:
  meterless_auto:
    provider: meterless
    model: meterless/auto
    price_class: mid
    context: 32768
    strip_think: true
    extra_body:
      chat_template_kwargs: { enable_thinking: false }
  meterless_deep: # strongest reasoning lane (planning, review)
    provider: meterless
    model: meterless/deep
    price_class: high
    context: 32768
    strip_think: true
  meterless_fast: # fastest lane (cheap classification, summaries)
    provider: meterless
    model: meterless/fast
    price_class: low
    context: 32768
    strip_think: true
    extra_body:
      chat_template_kwargs: { enable_thinking: false }
```

**Role chains (profile `meterless`):**
| Role | Chain |
|------|-------|
| main | `meterless_auto` → `local_main` |
| planner | `meterless_deep` → `meterless_auto` → `local_main` |
| worker | `meterless_auto` → `local_main` |
| cheap | `meterless_fast` → `meterless_auto` → `local_main` |
| escalation | `meterless_deep` → `local_main` |

### 2.4 `zetaris status` / `zetaris sql` — Structured Knowledge Store

```bash
# Probe
python -m barthelona zetaris status

# Read-only query (one SELECT/SHOW/DESCRIBE/WITH statement)
python -m barthelona zetaris sql "SELECT * FROM my_table LIMIT 10"
# or: zetaris sql --limit 100 "WITH cte AS (...) SELECT * FROM cte"
```

> **Full guide:** [`docs/zetaris-guide.md`](zetaris-guide.md) — installation, API key, SQL queries, `--facts-sql` injection, fact registration

**Environment variables:**
| Variable | Default | Required |
|----------|---------|----------|
| `ZETARIS_API_KEY` | — | Yes |
| `ZETARIS_REST_URL` | `http://localhost:8888/api/v1.0` | No |
| `ZETARIS_ORG_ID` | `1` | No |

**What it does:**

- `status`: Runs `SELECT 1` via the REST API; reports `online`, `unauthorized`, `offline`, or `unconfigured`
- `sql`: Sends one read-only statement to `POST /sql-editor/sqls/run` with fresh `X-Request-ID`, returns rows as text

**Integration with `chunked run`:**

```bash
python -m barthelona chunked run "task text" \
  --facts-sql "SELECT fact FROM knowledge WHERE topic = 'nasm'"
```

The query rows are prepended to chunk 1 as an untrusted `[ZETARIS FACTS]` block (wrapped by the injection guard).

### 2.5 `chunked run` — Long Tasks as Markovian Chunks

```bash
python -m barthelona chunked run "Write a NASM strlen function" \
  --profile meterless --role worker --out strlen.asm --code --assemble \
  --repair 2 --memory var/hmem.sqlite --domain assembly \
  --plan-role planner --review-role cheap \
  --stats var/runs.sqlite
```

**What it does:**

1. **Recalls** memories from H-MEM store (SQLite, domain-tagged)
2. **Optionally queries Zetaris** (`--facts-sql`) for untrusted facts
3. **Optionally plans** with `plan_role` (e.g., `planner`) → short numbered plan
4. **Runs the task** in bounded chunks (default 8K tokens/chunk, 800 carryover, max 24 chunks) through the `role`'s chain
5. **Optionally assembles** with NASM (`--assemble` implies `--code`); on failure, up to `--repair` retries with NASM errors fed back
6. **Optionally reviews** with `review_role` (advisory only; oracle decides)
7. **Optionally writes** H-MEM memories if the assemble oracle accepted (`pass`)
8. **Optionally logs** per-chunk statistics to SQLite (`--stats`)

**Key parameters:**
| Option | Default | Description |
|--------|---------|-------------|
| `--profile` | `meterless` | Catalog profile (local-only, hybrid, cloud, meterless) |
| `--role` | `worker` | Catalog role whose chain answers each chunk |
| `--chunk-tokens` | 8000 | Tokens per chunk (engine range 1000–128000) |
| `--carryover-tokens` | 800 | State tokens carried between chunks |
| `--max-chunks` | 24 | Upper bound on chunks (1–32) |
| `--repair` | 0 | Extra assemble attempts with errors (0–3) |
| `--memory` | — | H-MEM SQLite file for recall/write |
| `--domain` | `assembly` | H-MEM domain for ranking/tagging |
| `--plan-role` | — | Role to write a plan first (e.g., `planner`) |
| `--review-role` | — | Role to review output (advisory) |
| `--stats` | — | Run statistics SQLite database |
| `--expect-stdout`, `--expect-exit` | — | Run the assembled program in the Unicorn emulator and require this stdout and exit code (implies `--assemble`); a mismatch is repaired like an assembler error |
| `--single-shot` | off | One completion instead of chunks, for short tasks; `--assemble`, `--repair` and the expectations still apply |
| `--repair-role` | — | Role used for the repair attempts (for example `planner`) |

**Output:** Per-chunk table (served by, answered by, tokens, latency, fallbacks), final stop reason, and if `--out` given, the extracted code block written to that file.

---

## 3. Model Gateway (Working Skeleton)

The gateway (`src/barthelona/llm/gateway.py`) implements:

- **Role router**: walks the role's chain for the active profile
- **Fallback chains**: every chain ends in a local model (`local_main`)
- **Per-endpoint semaphores**: one in-flight call per local endpoint (LM Studio, Ollama, Meterless)
- **Provider backends**: `OpenAIChatBackend` (LM Studio, Ollama, DeepSeek, QwenCloud, Meterless), `OpenAIResponsesBackend` (OpenAI), `AnthropicBackend`, `GeminiBackend`, `FakeGateway` (tests)
- **Structured output**: json_schema (local), output_config (Anthropic), json_schema strict (OpenAI Responses), json_schema (Gemini), json_object + Pydantic repair (DeepSeek, DashScope)
- **Cost ledger**: every call's cost from API usage × catalog prices (long-context tiers, cache writes, off-peak discounts)
- **Circuit breakers** (transient/terminal), retries (transient only), output repair (max 2)

**What's NOT yet implemented (Phase 1):**

- Model-affinity scheduler (group calls by model to reuse prefix cache)
- Streaming for large max_tokens / long reasoning
- Full error taxonomy mapping per provider
- Reserve-then-settle budget enforcement

---

## 4. Training Data Collection (Opt-in, D-036)

```bash
# Check status
python -m barthelona training status

# Enable collection (per run, pinned at run start)
BARTHELONA_TRAINING_DATA_ENABLED=1 python -m barthelona ...
```

**What it collects (after tamper gate + ladder judgment):**

- One `TrainingSample` per code-producing model attempt
- Metadata in `samples.jsonl`; prompt/response texts in content-addressed `texts/<aa>/<sha256>.txt`
- Secrets redacted before writing
- **Not collected**: holdout benchmark attempts, deterministic nodes
- **Verdicts**: `rejected` (any level failed), `accepted` (none failed, at least one passed), `not_verified` (skipped/unsupported)

**Export (Phase 1):**

```bash
python -m barthelona training export  # trainer-ready files; local-model samples only by default
```

---

## 5. Verification: Test Projects That Pass Today

Two hand-written 3-module projects in `tests/projects/` pass the full MVP ladder (V0–V2, V5, V6):

| Project       | Dialect   | Modules                          | Command                                                                                                                |
| ------------- | --------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `nasm-triple` | NASM      | `main.asm`, `io.asm`, `math.asm` | `python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm -c contracts.yaml -t tests.yaml`     |
| `gas-triple`  | GAS Intel | `main.s`, `io.s`, `math.s`       | `python -m barthelona verify tests/projects/gas-triple --level V6 --dialect gas-intel -c contracts.yaml -t tests.yaml` |

Each has:

- `contracts.yaml` — `ContractRegistry` with symbols, structs, register contracts, stack contracts
- `tests.yaml` — `TestCase` list (V5 `c_harness`, V6 `io_golden`)
- Source files with matching module names

**Run with Docker (Linux host or WSL):**

```bash
# Build the images and start bart-tc (idempotent; Windows: wsl -d Ubuntu -e bash scripts/setup-toolchain.sh)
scripts/setup-toolchain.sh

# Run verification
python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm \
  --contracts tests/projects/nasm-triple/contracts.yaml \
  --tests tests/projects/nasm-triple/tests.yaml
```

---

## 6. Code Generation (Deterministic, No LLM)

The `contracts.codegen` module (`src/barthelona/contracts/codegen.py`) generates from a `ContractRegistry`:

- `gen/<module>.inc` — exports + own imports only (hash header, committed)
- `gen/stubs/<module>.asm` — exported functions trap with `ud2` (all-stub skeleton passes V0–V2)
- `gen/contracts.h` — C prototypes (`u8`..`u64`, `i8`..`i64`, `usize`, `char`, pointers), consts, struct offsets as enums
- `gen/harness/<test>.c` — V5 C harness calls function with integer inputs, exits 1 on mismatch
- `Makefile` (planned, emitted by `header_gen` node in Phase 1)

**Tamper gate** regenerates `gen/` from the registry and flags any missing/edited/extra file.

---

## 7. What Does NOT Work Yet (Phase 1+)

| Feature                                                                                  | Phase |
| ---------------------------------------------------------------------------------------- | ----- |
| Meta-Agentic Scrum engine (outer run graph, sprint loop)                                 | 1     |
| Streamlit UI (New request, Approvals, Sprint board, Live run, Review)                    | 1     |
| AI-composed sprint graphs (L0 templates, L1/L2 composition)                              | 1/2   |
| `architect`, `refine_backlog`, `test_author`, `sprint_planner`, `codegen`, `fixer` nodes | 1     |
| Human gates G0–G6 (except CLI approximations)                                            | 1     |
| V3 (Capstone ABI lint), V4 (Unicorn emulator)                                            | 2     |
| Edit mode for external projects (import, detect target, repo map, inferred contracts)    | 3     |
| FASM, Win64, ELF32, asmc/UASM, ml64, boot sector presets                                 | 4     |
| Policy Lab, web research, OpenTelemetry                                                  | 5     |
| C family, Web/2D families                                                                | 6     |
| Pure-assembly TLS 1.3 + HTTP/2 proxy (reference ambition)                                | 7     |

---

## 8. Environment Requirements

| Component              | Windows                                    | Linux                                |
| ---------------------- | ------------------------------------------ | ------------------------------------ |
| Python                 | 3.13 (conda)                               | 3.13 (conda)                         |
| Docker                 | WSL2 Ubuntu 26.04                          | Native Docker                        |
| WSL                    | Ubuntu 26.04 distro                        | N/A                                  |
| LM Studio              | `http://127.0.0.1:1234/v1`                 | `http://127.0.0.1:1234/v1` or remote |
| Meterless (Nightshift) | Optional, `http://127.0.0.1:8088/v1`       | Optional                             |
| Zetaris                | Optional, `http://localhost:8888/api/v1.0` | Optional                             |
| Qdrant (project)       | `docker/qdrant/compose.yaml` in WSL        | Same compose                         |

**WSL memory cap (required for local model):**

```ini
# %UserProfile%\.wslconfig
[wsl2]
memory=8GB
processors=8
```

Then `wsl --shutdown`.

---

## 9. Directory Layout (Key Paths)

```
barthelona/
├── config/
│   ├── models.yaml           # Model catalog, role chains, budgets
│   └── toolchains.lock.json  # Generated by `probe`
├── docker/
│   ├── toolchain/Dockerfile  # bart-tc (nasm, yasm, fasm, binutils, gcc, gdb, make)
│   ├── runner/Dockerfile     # bart-run (minimal runtime)
│   └── qdrant/compose.yaml   # Project Qdrant on 127.0.0.1:6343/6344
├── src/barthelona/
│   ├── cli/                  # All CLI commands
│   ├── domain/               # Pydantic v2 models (source of truth)
│   ├── executors/            # FakeExecutor, WslExecutor, AgentExecutor, SandboxExecutor
│   ├── toolchains/           # NasmAdapter, GasIntelAdapter, GasAttAdapter
│   ├── verification/         # Ladder, registry, native_asm, golden, harness
│   ├── contracts/            # Codegen, loader, tamper gate
│   ├── llm/                  # Gateway, catalog, backends, meterless, zetaris, markovian
│   ├── persistence/          # SQLite WAL store (runs, events, gates, ledger)
│   └── training/             # Dataset writer/reader, redaction
├── tests/
│   ├── projects/             # nasm-triple, gas-triple (pass V0-V2, V5, V6)
│   ├── abi_mutation/         # Good/bad snippets per violation kind
│   └── fixtures/diagnostics/ # Captured tool output per version
├── var/                      # gitignored: app.sqlite, checkpoints, runs/, kb/, training/
└── workspaces/               # gitignored: one git repo per project
```

---

## 10. Next Steps for Contributors

1. **Run the probe** to lock toolchain versions:

   ```bash
   scripts/setup-toolchain.sh   # Windows: wsl -d Ubuntu -e bash scripts/setup-toolchain.sh
   python -m barthelona probe
   ```

2. **Run the verification ladder** on the test projects:

   ```bash
   python -m barthelona verify tests/projects/nasm-triple --level V6 --dialect nasm \
     --contracts tests/projects/nasm-triple/contracts.yaml \
     --tests tests/projects/nasm-triple/tests.yaml
   ```

3. **Try the Meterless integration** (if you have Nightshift running):

   ```bash
   export METERLESS_BASE_URL=http://127.0.0.1:8088/v1
   export METERLESS_RUNTIME_TOKEN=your-runtime-token
   python -m barthelona meterless status
   python -m barthelona chunked run "Write NASM strlen" --profile meterless --assemble --repair 2
   ```

4. **Try Zetaris** (if you have a Zetaris instance):

   ```bash
   export ZETARIS_API_KEY=your-key
   python -m barthelona zetaris status
   python -m barthelona zetaris sql "SELECT 1"
   ```

5. **Read the architecture** for the full design: [`docs/architecture.md`](architecture.md)

6. **Check the roadmap** for phase deliverables: [`docs/roadmap.md`](roadmap.md)

---

_Last updated: 2026-10-24. This document reflects the actual runnable state of the Phase 0 deterministic spine. The engine and UI are Phase 1 deliverables._

---

## 5. The Worker (Phase 1a, slices 1-3)

`python -m barthelona worker [--once]` claims queued runs from `var/app.sqlite`, runs the outer run graph and
parks each run at gate G1. The graph so far is `preflight` (unsupported presets stop the run as
`unsupported_target`), `intake` (language, English goal, entities), `spec` (a `ProjectSpec` draft),
`test_author` (golden-I/O acceptance tests; the model is told which requirement is uncovered),
`validate_spec` (every requirement has a test; writes `var/runs/<run_id>/spec.json` and `tests.json`), the G1 gate
and `finalize`. The request text is read from
`var/runs/<run_id>/request.txt`; each node is one JSON model call through the gateway with the run's profile,
recorded in the LLM-call ledger, and a bad reply is sent back once (two bad replies stop the run as
`max_attempts`; an exhausted chain stops it as `no_model_available`). Not built yet: G0 questions, a reference
model and the emulator cross-check of the test examples. `worker --facts-sql "SELECT ..."` reads one Zetaris
statement per run (needs `ZETARIS_API_KEY`) and adds its rows to the spec and test-author prompts, marked as
untrusted data; a failing Zetaris stops the run as `infra_error`. The tables to load are in
`knowledge/zetaris/`. A `resume` command with `approve` or `reject` continues the run;
`reject` and `cancel` stop it as `human_abort`; a crash is recovered from `var/checkpoints.sqlite`. `approve` stops
the run with `infra_error` ("not built yet") until the next slices (intake and spec, architect and scaffold, the
sprint loop) add their nodes. There is no UI page for it yet; the commands go in through the store
(`Store.enqueue_command`).
