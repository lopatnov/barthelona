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

This guide prepares you to demonstrate **Barthelona** — a local-first agentic system that creates or edits multi-file assembly projects from natural-language requests — using the three hackathon layers:

| Layer     | Technology                             | Role in Barthelona                                                                                            |
| --------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **DATA**  | Zetaris                                | Structured knowledge store for assembler facts (syscalls, instructions, ABI rules) injected via `--facts-sql` |
| **BUILD** | Cursor + Barthelona                    | Development environment; Barthelona's `chunked run` with Markovian Engine (H-MEM, bounded chunks)             |
| **POWER** | Meterless Nightshift + NVIDIA Nemotron | Model provider routing through lanes (Race/Judge/Verify) with local fallback                                  |

**Eligibility**: All three layers must be running on your machine.

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

```bash
# 1. Sign in to Zetaris registry (use command from 1.1)
docker login registry.zetaris.com -u <username> -p <password>

# 2. Clone getting-started recipes
git clone https://github.com/zetaris/getting-started.git
cd getting-started

# 3. Start Zetaris (downloads images, takes 30-45 min first run)
docker compose up -d

# 4. Verify it's running
curl -s http://localhost:8888/api/v1.0/health
# Should return: {"status":"ok"}
```

### 1.5 Create API Key

1. Open Zetaris web UI: http://localhost:8888
2. Log in (default credentials from bundle)
3. **Settings → API Keys → Generate New Key**
4. Copy the key — you won't see it again!

### 1.6 Test Zetaris Connection

```bash
# Set env vars for this session
export ZETARIS_API_KEY="your-key-here"
export ZETARIS_REST_URL="http://localhost:8888/api/v1.0"
export ZETARIS_ORG_ID="1"

# Test query
curl -H "Authorization: Bearer $ZETARIS_API_KEY" \
     -H "X-Org-ID: $ZETARIS_ORG_ID" \
     -H "X-Request-ID: $(uuidgen)" \
     -X POST "$ZETARIS_REST_URL/sql-editor/sqls/run" \
     -d '{"sql": "SELECT 1"}'
# Should return rows: [[1]]
```

### 1.7 Register Assembler Facts (Manual — Required for Demos)

Since automated ingestion isn't ready yet, manually create tables with assembler knowledge:

```bash
# In Zetaris SQL editor (web UI) or via API:

# Syscalls table
CREATE TABLE barthelona_syscalls (
    name VARCHAR(64) PRIMARY KEY,
    nr INTEGER NOT NULL,
    args VARCHAR(256),
    arch VARCHAR(16) DEFAULT 'x86-64',
    abi VARCHAR(16) DEFAULT 'sysv64'
);

# Insert key syscalls
INSERT INTO barthelona_syscalls (name, nr, args) VALUES
('sys_read', 0, 'fd, buf, count'),
('sys_write', 1, 'fd, buf, count'),
('sys_open', 2, 'pathname, flags, mode'),
('sys_close', 3, 'fd'),
('sys_exit', 60, 'error_code'),
('sys_getpid', 39, ''),
('sys_brk', 12, 'addr');

# Instructions table (NASM Appendix F subset)
CREATE TABLE barthelona_instructions (
    mnemonic VARCHAR(32),
    operands VARCHAR(128),
    encoding VARCHAR(64),
    cpu_flags VARCHAR(64),
    isa_ext VARCHAR(32),
    dialect VARCHAR(16) DEFAULT 'nasm',
    arch VARCHAR(16) DEFAULT 'x86-64'
);

-- Insert common instructions
INSERT INTO barthelona_instructions (mnemonic, operands, encoding, cpu_flags, isa_ext) VALUES
('mov', 'r/m64, r64', '48 89 /r', 'none', 'BASE'),
('mov', 'r64, r/m64', '48 8B /r', 'none', 'BASE'),
('lea', 'r64, m', '48 8D /r', 'none', 'BASE'),
('call', 'rel32', 'E8 cd', 'none', 'BASE'),
('ret', '', 'C3', 'none', 'BASE'),
('syscall', '', '0F 05', 'RCX,R11', 'BASE'),
('xor', 'r64, r/m64', '48 31 /r', 'SF,ZF,PF,CF,OF', 'BASE');
```

### 1.8 Verify Facts Are Queryable

```bash
python -m barthelona zetaris sql "SELECT name, nr, args FROM barthelona_syscalls WHERE nr < 10"
# Should show sys_read, sys_write, sys_open, sys_close
```

**✅ You're done with DATA when:** `python -m barthelona zetaris status` prints `online` and queries return rows.

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

### 2.4 Install Meterless Engines (Markovian, H-MEM)

The engines are already integrated in Barthelona's source:

```bash
# Verify they're available
python -c "from barthelona.llm.markovian import MarkovianEngine; print('Markovian OK')"
python -c "from barthelona.llm.hmem import HMemStore; print('H-MEM OK')"
```

### 2.5 Explore Prompt Library

Barthelona uses prompt templates from `bench/prompts/` and `policies/v1/prompts/`:

```bash
ls bench/prompts/
# single.md.j2, fix.md.j2, c.md.j2
```

### 2.5 Cursor Integration Tips

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

#### 3.1.3 Configure Lanes (Critical: Need 2+ Different Model Families)

**Nightshift UI → NIGHT → LANES → Add Lane:**

| Lane Name | Duty   | Model                               | Purpose                        |
| --------- | ------ | ----------------------------------- | ------------------------------ |
| `race`    | Race   | `nemotron-3.5-lightning-30b-a3b`    | Primary coding                 |
| `judge`   | Judge  | `gpt-4o-mini` or different Nemotron | Review (MUST differ from Race) |
| `verify`  | Verify | Another model                       | Validation                     |

> ⚠️ **Critical**: A model never grades its own answers. You MUST have at least two lanes with different model families, or Nightshift shows a red warning.

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

### 3.2 Option B: Direct NVIDIA API (Alternative)

If not using Nightshift, configure directly in `config/models.yaml`:

```yaml
providers:
  nvidia:
    kind: openai_chat
    base_url: https://integrate.api.nvidia.com/v1
    api_key_env: NVIDIA_API_KEY
    local: false
    network: internet
    enabled: true

models:
  nemotron_3b:
    provider: nvidia
    model: nvidia/nemotron-3.5-lightning-30b-a3b
    price_class: mid
    context: 32768
```

Add `NVIDIA_API_KEY` to `.env`.

### 3.3 Local Fallback Model (LM Studio)

For resilience when cloud fails:

1. Install LM Studio: https://lmstudio.ai
2. Download model: **Qwen3-Coder-30B-A3B** (Q4, ~17–19 GB) or **gpt-oss-20b**
3. Load with: Context 16384, q8_0 KV-cache if available
4. Start server: **LM Studio → Local Server → Start** (port 1234)
5. Verify: http://127.0.0.1:1234/v1/models

Barthelona's `meterless` profile automatically falls back to `local_main` (LM Studio).

### 3.4 WSL Memory Cap (Windows Only, Required for Local Model)

Create `%UserProfile%\.wslconfig`:

```ini
[general]
instanceIdleTimeout=-1  # never stop distro when idle

[wsl2]
memory=8GB              # leave RAM for LM Studio on Windows
processors=8
```

Then: `wsl --shutdown`

**✅ You're done with POWER when:** `python -m barthelona meterless status` prints `online` and you have a local fallback in LM Studio.

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

# 5. Run integration demo (hello world with memory)
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# 6. Run again to show memory recall (should use fewer chunks)
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# 7. Show stats
python -m barthelona chunked stats
# → Compare chunks= between runs
```

**✅ All layers integrated when:** All 7 steps pass without errors.

---

## Demo Scenarios

Prepare these three demo scenarios for the hackathon:

### Demo 1: Memory Proof (Hello World + H-MEM)

**What it shows:** H-MEM recall across runs — second run uses fewer chunks.

```bash
# Run 1: Learn
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# Run 2: Recall (should be faster, fewer chunks)
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# Show stats
python -m barthelona chunked stats
```

**Key talking points:**

- "First run: model learns from scratch, takes N chunks"
- "Second run: H-MEM recalls DECISIONS/CONTEXT, takes fewer chunks"
- "Assembler (NASM) is the oracle — only `assemble: pass` writes to memory"
- "Markovian Engine keeps prompt flat (peak_prompt stays constant)"

### Demo 2: Multi-Chunk Generation (FizzBuzz)

**What it shows:** Markovian chunking for tasks exceeding single-chunk capacity.

```bash
# Requires LM Studio with Qwen coder + Codestral (local-coder profile)
python -m barthelona chunked run @demos/fizzbuzz/task.txt \
  --profile local-coder --plan-role planner --review-role cheap \
  --repair-role planner --chunk-tokens 2000 --carryover-tokens 128 \
  --max-chunks 8 --assemble --repair 2 \
  --expect-stdout "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz\n" \
  --expect-exit 0 \
  --memory var/proof/fb-hmem.sqlite --stats var/proof/fb-runs.sqlite \
  --out var/proof/fizzbuzz.asm
```

**Key talking points:**

- "Task too long for one chunk → Markovian Engine splits into bounded chunks"
- "Carryover tokens (128) pass state between chunks"
- "Planner (deep) → Worker (auto) → Review (fast) role chains"
- "Emulator validates behavior, not just syntax"

### Demo 3: Zetaris Fact Injection

**What it shows:** External structured knowledge injected into generation.

```bash
# Query Zetaris for syscall facts, inject into chunk 1
python -m barthelona chunked run "Write a NASM program that prints 'Hello' using sys_write" \
  --profile meterless \
  --facts-sql "SELECT nr, args FROM barthelona_syscalls WHERE name = 'sys_write'" \
  --assemble --repair 2 \
  --expect-stdout "Hello\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out zetasys.asm
```

**Key talking points:**

- "Zetaris provides exact facts (syscall numbers, args) — no hallucination"
- "Facts injected as untrusted `[ZETARIS FACTS]` block in chunk 1"
- "Injection guard prevents prompt injection"
- "Model uses facts, but assembler/emulator still validate"

---

## Running the Demos

### Quick Demo Script (All in One)

```powershell
# Save as demo.ps1 and run from repo root in activated terminal

Write-Host "=== BARTHELONA HACKATHON DEMO ===" -ForegroundColor Cyan

# 1. Verify all layers
Write-Host "`n1. Verifying layers..." -ForegroundColor Yellow
python -m barthelona zetaris status
python -m barthelona meterless status
python -m barthelona version

# 2. Demo 1: Memory Proof
Write-Host "`n2. Demo 1: H-MEM Memory Proof (Hello World)..." -ForegroundColor Yellow
python -m barthelona chunked run @demos/hello/task.txt `
  --profile meterless --assemble --repair 2 `
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 `
  --memory var/hmem.sqlite --stats var/runs.sqlite `
  --out demos/hello/hello.asm

Write-Host "`n   Running second time to show memory recall..." -ForegroundColor Green
python -m barthelona chunked run @demos/hello/task.txt `
  --profile meterless --assemble --repair 2 `
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 `
  --memory var/hmem.sqlite --stats var/runs.sqlite `
  --out demos/hello/hello.asm

python -m barthelona chunked stats

# 3. Demo 2: Zetaris Fact Injection
Write-Host "`n3. Demo 3: Zetaris Fact Injection..." -ForegroundColor Yellow
python -m barthelona chunked run "Write NASM _start that writes 'Zetaris OK' via sys_write" `
  --profile meterless `
  --facts-sql "SELECT nr, args FROM barthelona_syscalls WHERE name = 'sys_write'" `
  --assemble --repair 2 `
  --expect-stdout "Zetaris OK\n" --expect-exit 0 `
  --memory var/hmem.sqlite --stats var/runs.sqlite `
  --out zetasys.asm

Write-Host "`n=== DEMO COMPLETE ===" -ForegroundColor Cyan
```

### What Judges Should See

| Demo         | Expected Output                   | Key Evidence           |
| ------------ | --------------------------------- | ---------------------- |
| Memory Proof | Run 2 `chunks=` < Run 1 `chunks=` | H-MEM working          |
| FizzBuzz     | `assemble: pass` + correct output | Multi-chunk + emulator |
| Zetaris      | Uses correct syscall number (1)   | Fact injection working |

---

## Troubleshooting

### Zetaris Issues

| Symptom               | Fix                                                                   |
| --------------------- | --------------------------------------------------------------------- |
| `unauthorized`        | Regenerate API key in Zetaris UI; update `ZETARIS_API_KEY`            |
| `offline`             | `docker compose up -d` in getting-started dir; check Docker resources |
| `unconfigured`        | Set `ZETARIS_API_KEY` in env; reload shell                            |
| Query returns no rows | Check table name (`barthelona_syscalls`); verify inserts committed    |

### Meterless/Nightshift Issues

| Symptom                | Fix                                                     |
| ---------------------- | ------------------------------------------------------- |
| `unauthorized`         | Copy fresh token from Nightshift Console; update `.env` |
| `offline`              | Start Nightshift app; check port 8088                   |
| Red "no Judge lane"    | Add Judge lane with **different model family**          |
| Falls to `local_main`  | Check Nightshift logs; stop LM Studio to see real error |
| Empty/truncated output | Increase `--chunk-tokens` (default 8000)                |

### Barthelona Issues

| Symptom                  | Fix                                                                   |
| ------------------------ | --------------------------------------------------------------------- |
| `assemble: unavailable`  | Install NASM (https://www.nasm.us/) or set `BARTHELONA_NASM`          |
| `assemble: fail`         | Read NASM errors; sharpen task; re-run                                |
| Docker container missing | `scripts/setup-toolchain.sh` (or WSL equivalent)                      |
| `chunks=` not decreasing | Ensure Run 1 had `assemble: pass` (only successful runs write memory) |

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
| **Lane**                  | Model + role in Nightshift (Race/Judge/Verify)                    |
| **Markovian Engine**      | Long generation as bounded chunks with flat context               |
| **Oracle**                | Tool that decides correctness (NASM, linker, emulator)            |
| **Race Lane**             | Primary model doing the work                                      |
| **Judge Lane**            | Different model reviewing/validating                              |
| **Zetaris**               | Data virtualization platform; SQL interface for structured facts  |
| **`--facts-sql`**         | CLI flag injecting Zetaris query results into chunk 1             |
| **`assemble: pass/fail`** | NASM verdict — the true oracle                                    |

---

## Quick Reference Card

```bash
# ===== ONE-TIME SETUP =====
# 1. Zetaris (start first — 30-45 min)
cd getting-started && docker compose up -d
# Create API key in Zetaris UI → export ZETARIS_API_KEY=...

# 2. Barthelona
.\scripts\create_env.ps1 && . .\scripts\activate.ps1
scripts\setup-toolchain.sh
python -m barthelona probe

# 3. Nightshift
# Install from meterless.ai → add NVIDIA provider → add Race+Judge lanes
# Copy runtime token → .env: METERLESS_RUNTIME_TOKEN=...

# 4. LM Studio (local fallback)
# Download Qwen3-Coder-30B-A3B → load context 16K → start server

# ===== DAILY START =====
. .\scripts\activate.ps1
python -m barthelona zetaris status   # → online
python -m barthelona meterless status # → online

# ===== DEMO COMMANDS =====
# Memory proof (run twice!)
python -m barthelona chunked run @demos/hello/task.txt `
  --profile meterless --assemble --repair 2 `
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 `
  --memory var/hmem.sqlite --stats var/runs.sqlite `
  --out demos/hello/hello.asm
python -m barthelona chunked stats

# Zetaris injection
python -m barthelona chunked run "NASM sys_write 'Hello'" `
  --profile meterless `
  --facts-sql "SELECT nr, args FROM barthelona_syscalls WHERE name='sys_write'" `
  --assemble --repair 2 --expect-stdout "Hello\n" --expect-exit 0 `
  --out zetasys.asm
```

---

## Hackathon Day Checklist

- [ ] Zetaris running (`docker compose ps` shows all Up)
- [ ] Zetaris API key in env, `zetaris status` → online
- [ ] Nightshift running, `meterless status` → online + 3 routes
- [ ] Two+ lanes with **different model families** (Race + Judge)
- [ ] LM Studio running with local model (fallback)
- [ ] Barthelona env activated, `doctor` passes
- [ ] `verify` passes on nasm-triple
- [ ] Demo 1 (hello) runs twice, shows chunk reduction
- [ ] Demo 3 (Zetaris) injects correct syscall number
- [ ] `smoke_test.py` passes (if provided by hackathon)

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
