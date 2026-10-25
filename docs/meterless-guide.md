# Meterless (Nightshift) Integration Guide

Complete step-by-step guide to setting up and using Meterless Nightshift as the primary model provider for Barthelona.

---

## Table of Contents

1. [What is Meterless Nightshift?](#what-is-meterless-nightshift)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Nightshift Configuration](#nightshift-configuration)
5. [Barthelona Configuration](#barthelona-configuration)
6. [Verification](#verification)
7. [Running Tasks with Meterless](#running-tasks-with-meterless)
8. [Profiles and Role Chains](#profiles-and-role-chains)
9. [Memory (H-MEM) with Meterless](#memory-h-mem-with-meterless)
10. [Troubleshooting](#troubleshooting)
11. [Advanced Configuration](#advanced-configuration)
12. [References](#references)

---

## What is Meterless Nightshift?

**Meterless Nightshift** is a local runtime that routes requests to multiple model "lanes" (different models for different purposes: fast classification, deep reasoning, balanced coding, etc.). It serves an OpenAI-compatible API at `http://127.0.0.1:8088/v1`.

Key concepts:

- **Lane** = a specific model + role (e.g., "Race" for fast coding, "Judge" for review)
- **Race lane** = the primary model that does the work
- **Judge/Verify lane** = a different model that reviews/validates (a model never grades its own answers)
- **Provider** = where the model comes from (NVIDIA Nemotron, local LM Studio, etc.)

Barthelona's `meterless` profile uses three lanes:

- `meterless/auto` (balanced) → worker, main
- `meterless/deep` (strongest reasoning) → planner, escalation
- `meterless/fast` (cheapest) → cheap, review

---

## Prerequisites

| Requirement        | Details                                                                                   |
| ------------------ | ----------------------------------------------------------------------------------------- |
| **OS**             | Windows 11 (tested) or Linux                                                              |
| **Docker**         | For `verify` (V5/V6) and `probe` — see [`docs/runbook.md`](runbook.md) §2                 |
| **WSL2**           | Ubuntu 26.04 (Windows only) — see [`docs/runbook.md`](runbook.md) §2                      |
| **Python**         | 3.13 via conda (managed by `scripts/create_env.ps1`)                                      |
| **NVIDIA API Key** | Free from [NVIDIA](https://build.nvidia.com/) — lives only in Nightshift, never in `.env` |
| **RAM**            | 16 GB+ recommended for local fallback model                                               |

---

## Installation

### 1. Set up Python environment

```powershell
# Windows PowerShell
.\scripts\create_env.ps1
. .\scripts\activate.ps1
.\scripts\doctor.ps1
```

```bash
# Git Bash / Linux
scripts/create_env.sh
source scripts/activate.sh
scripts/doctor.sh
```

### 2. Install and start Nightshift

1. Download the Nightshift app from https://meterless.ai
2. Install and launch it
3. Verify it's running: open http://127.0.0.1:8088/v1/models in a browser (should return JSON)

### 3. Configure Nightshift Providers

1. In Nightshift UI: **Setup → Providers**
2. Click **Add Provider** → select **NVIDIA**
3. Paste your NVIDIA API key (from https://build.nvidia.com/)
4. Click **Save** — the key stays in Nightshift only, never in `.env`

### 4. Configure Nightshift Lanes

Go to **NIGHT → LANES** and add at least two lanes:

| Lane Name | Duty  | Suggested Model                                                  | Purpose                                             |
| --------- | ----- | ---------------------------------------------------------------- | --------------------------------------------------- |
| `race`    | Race  | a Nemotron model from Nightshift's list (the id here before was not re-checked; the dev PC's lane answered as `nvidia/nemotron-3-ultra-550b-a55b`) | Primary coding model                                |
| `judge`   | Judge | Different model family (e.g., `gpt-4o-mini` or another Nemotron) | Review/validation — **must be different from Race** |

> ⚠️ **Critical**: A model never grades its own answers. You MUST have at least two lanes with different model families, or Nightshift will show a red warning.

### 5. Get the Runtime Token

1. In Nightshift: **Console → Runtime Token**
2. Copy the token
3. Add to `.env` (create from `.env.example` if needed):

```bash
# .env (gitignored — never commit!)
METERLESS_RUNTIME_TOKEN=your-token-here
# Optional, only if your Nightshift URL differs:
# METERLESS_BASE_URL=http://127.0.0.1:8088/v1
```

---

## Barthelona Configuration

The Meterless integration is pre-configured in [`config/models.yaml`](config/models.yaml). Key sections:

### Provider Definition

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
    headers:
      meterless-app: barthelona
      meterless-scope: user
```

### Model Definitions

```yaml
models:
  meterless_auto: # balanced — worker, main
    provider: meterless
    model: meterless/auto
    price_class: mid
    context: 32768
    strip_think: true
    extra_body:
      chat_template_kwargs: { enable_thinking: false }

  meterless_deep: # strongest reasoning — planner, escalation
    provider: meterless
    model: meterless/deep
    price_class: high
    context: 32768
    strip_think: true

  meterless_fast: # fastest/cheapest — cheap, review
    provider: meterless
    model: meterless/fast
    price_class: low
    context: 32768
    strip_think: true
    extra_body:
      chat_template_kwargs: { enable_thinking: false }
```

### Role Chains (Profile `meterless`)

| Role         | Chain (falls back left → right)                    |
| ------------ | -------------------------------------------------- |
| `main`       | `meterless_auto` → `local_main`                    |
| `planner`    | `meterless_deep` → `meterless_auto` → `local_main` |
| `worker`     | `meterless_auto` → `local_main`                    |
| `cheap`      | `meterless_fast` → `meterless_auto` → `local_main` |
| `escalation` | `meterless_deep` → `local_main`                    |

Every chain ends in `local_main` (your local LM Studio/Ollama model) for resilience.

---

## Verification

Test that everything is connected:

```bash
# Check Nightshift connectivity and list available routes
python -m barthelona meterless status
```

**Expected output:**

```
Meterless status: online
Routes: meterless/auto, meterless/deep, meterless/fast
```

**Common responses:**
| Status | Meaning |
|--------|---------|
| `online` | ✅ Connected, routes listed |
| `unauthorized` | ❌ Wrong/missing `METERLESS_RUNTIME_TOKEN` |
| `offline` | ❌ Nightshift not running or unreachable |

---

## Running Tasks with Meterless

### Basic `chunked run` with Meterless

```bash
python -m barthelona chunked run "Write a NASM strlen function" \
  --profile meterless \
  --role worker \
  --out strlen.asm \
  --code --assemble \
  --repair 2 \
  --memory var/hmem.sqlite \
  --domain assembly \
  --plan-role planner \
  --review-role cheap \
  --stats var/runs.sqlite
```

### Key Flags Explained

| Flag                       | Purpose                                                      |
| -------------------------- | ------------------------------------------------------------ |
| `--profile meterless`      | Uses the Meterless role chains                               |
| `--role worker`            | Which role's chain answers each chunk                        |
| `--assemble`               | Run NASM on output (oracle decides pass/fail)                |
| `--repair 2`               | On NASM error, feed error back to model (up to 2 retries)    |
| `--expect-stdout "..."`    | Run in Unicorn emulator, require exact stdout                |
| `--expect-exit 0`          | Require exit code 0 (implies `--assemble`)                   |
| `--memory var/hmem.sqlite` | H-MEM: recall prior run facts, write new ones on success     |
| `--plan-role planner`      | Run planner chain first for a numbered plan                  |
| `--review-role cheap`      | Run cheap chain for advisory review after                    |
| `--stats var/runs.sqlite`  | Log per-chunk statistics (model, tokens, latency, fallbacks) |

### Using `@file` for Task Input

```bash
# Read task from file (one command, PowerShell)
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm
```

---

## Profiles and Role Chains

Barthelona supports multiple profiles in [`config/models.yaml`](config/models.yaml):

| Profile      | Use Case                                 | Cloud?                        |
| ------------ | ---------------------------------------- | ----------------------------- |
| `local-only` | Fully offline, local LM Studio only      | No                            |
| `meterless`  | **Primary: Nightshift + local fallback** | Yes (Nightshift)              |
| `hybrid`     | Cloud providers + local fallback         | Yes (Anthropic, OpenAI, etc.) |
| `cloud`      | Cloud only, no local fallback            | Yes                           |

### Switching Profiles

```bash
# Use Meterless (default for hackathon)
--profile meterless

# Use local-only (no cloud, fully offline)
--profile local-only

# Use hybrid (Anthropic → OpenAI → Gemini → DeepSeek → local)
--profile hybrid
```

### Custom Role Override

```bash
# Use a specific role's chain for this run
--role planner        # deep reasoning chain
--role worker         # balanced coding chain (default)
--role cheap          # fast/cheap chain
--role escalation     # flagship-first chain
```

---

## Memory (H-MEM) with Meterless

H-MEM (Hierarchical Memory) lets Barthelona **recall facts from previous successful runs** and **store new facts** for future runs.

### How It Works

1. **On first run**: No memory → model solves from scratch
2. **On success**: DECISIONS and CONTEXT from the final chunk written to `var/hmem.sqlite`
3. **On subsequent runs**: Relevant facts recalled and prepended to chunk 1
4. **Result**: Fewer chunks needed, faster convergence

### Running the Memory Proof (demos/hello/)

```bash
# Run 1: learns the task
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# Run 2: recalls from memory, should use fewer chunks
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# Compare statistics
python -m barthelona chunked stats
```

**Expected**: Run 2 shows fewer `chunks=` than Run 1 (if both `assemble: pass`).

### Memory Database

- Location: `var/hmem.sqlite` (gitignored)
- Schema: `domain`, `key`, `value`, `source`, `alpha`, `beta`, `created`, `last_confirmed`
- Only successful runs (`assemble: pass`) write to memory
- Domain-tagged: `--domain assembly` isolates assembly facts

---

## Troubleshooting

### `meterless status` says `unauthorized`

| Cause                                       | Fix                                                                               |
| ------------------------------------------- | --------------------------------------------------------------------------------- |
| Missing `METERLESS_RUNTIME_TOKEN` in `.env` | Add token from Nightshift Console                                                 |
| Token expired/regenerated                   | Copy new token from Nightshift Console                                            |
| `.env` not loaded in shell                  | Use `. .\scripts\activate.ps1` (note leading dot) or `source scripts/activate.sh` |

### `assemble: unavailable`

| Cause              | Fix                                                      |
| ------------------ | -------------------------------------------------------- |
| NASM not installed | Install from https://www.nasm.us/                        |
| NASM not in PATH   | Set `BARTHELONA_NASM=C:\path\to\nasm.exe` or `NASM_PATH` |

### Chunk falls through to `local_main`

| Cause                                        | Fix                                                     |
| -------------------------------------------- | ------------------------------------------------------- |
| Nightshift lane failed (timeout, rate limit) | Check Nightshift logs; stop LM Studio to see real error |
| Lane model not loaded in Nightshift          | Ensure the lane's model is loaded in Nightshift UI      |
| NVIDIA key rejected                          | Re-enter key in Nightshift Providers tab                |

### Lane shows timeout / "provider refused the key"

| Cause                  | Fix                                                           |
| ---------------------- | ------------------------------------------------------------- |
| NVIDIA API key invalid | Regenerate at https://build.nvidia.com/, update in Nightshift |
| Network issue          | Check firewall; Nightshift needs outbound HTTPS               |

### Empty/truncated answers from Nemotron reasoning model

| Cause                                  | Fix                                      |
| -------------------------------------- | ---------------------------------------- |
| Output budget exhausted while thinking | Increase `--chunk-tokens` (default 8000) |

### Red "no lane has duty Judge or Verify" in Nightshift

| Cause                           | Fix                                                                                 |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| Only one lane (Race) configured | Add a second lane with **Judge** or **Verify** duty on a **different model family** |

### `stop_reason=green` but `assemble: fail`

| Explanation                                               | Fix                                              |
| --------------------------------------------------------- | ------------------------------------------------ |
| `green` = chunk loop finished; `assemble:` = NASM verdict | Read NASM errors in output; sharpen task; re-run |

---

## Advanced Configuration

### Using Meterless on Another PC (LAN)

1. On model PC: Enable **Serve on Local Network** in Nightshift settings
2. Allow port 8088 in firewall (trusted LAN only — no auth by default)
3. In Barthelona `.env` or `config/models.yaml`:

```yaml
# config/models.yaml
providers:
  meterless:
    base_url: http://<lan-ip>:8088/v1 # use IP, not localhost
```

### Custom Model in Nightshift

To use a different model behind a lane:

1. Nightshift: **Setup → Providers** → add provider (Ollama, LM Studio, OpenAI, etc.)
2. **NIGHT → LANES** → edit lane → select new model
3. No Barthelona config change needed — routes are discovered via `/v1/models`

### Adjusting Timeouts

For slow models or long reasoning:

```yaml
# config/models.yaml
providers:
  meterless:
    timeout_s: 300 # 5 minutes (default 180s)
```

### Disabling Thinking for Specific Models

Some models (Nemotron) have thinking enabled by default. Disable via `extra_body`:

```yaml
models:
  my_model:
    extra_body:
      chat_template_kwargs: { enable_thinking: false }
```

---

## References

| Document                        | Link                                                                                              |
| ------------------------------- | ------------------------------------------------------------------------------------------------- |
| Quickstart (includes Meterless) | [`docs/quickstart.md`](quickstart.md)                                                             |
| Commands (meterless status)      | [`docs/quickstart.md`](quickstart.md#24-meterless-status-is-nightshift-reachable)       |
| Runbook (environment setup)     | [`docs/runbook.md`](runbook.md#4-lm-studio-local-models)                                          |
| Hackathon Demo Notes            | [`docs/hackathon-demo.md`](hackathon-demo.md)                                                     |
| Architecture (Model Gateway)    | [`docs/architecture.md`](architecture.md#16-llm-routing-structured-output-context)                |
| ADR D-029                       | [Multi-provider model catalog](adr/D-029-multi-provider-model-catalog.md)                         |
| ADR D-030                       | [Provider resilience and optional budgets](adr/D-030-provider-resilience-and-optional-budgets.md) |
| Demo: hello (memory proof)      | [`demos/hello/README.md`](../demos/hello/README.md)                                               |
| Demo: fizzbuzz (multi-chunk)    | [`demos/fizzbuzz/README.md`](../demos/fizzbuzz/README.md)                                         |

---

## Quick Reference Card

```bash
# 1. Start Nightshift, add NVIDIA key, add Race + Judge lanes
# 2. Copy runtime token to .env
METERLESS_RUNTIME_TOKEN=xxx

# 3. Verify
python -m barthelona meterless status

# 4. Run hello demo (memory proof) — twice!
python -m barthelona chunked run @demos/hello/task.txt \
  --profile meterless --assemble --repair 2 \
  --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 \
  --memory var/hmem.sqlite --stats var/runs.sqlite \
  --out demos/hello/hello.asm

# 5. Check stats
python -m barthelona chunked stats
```

---

_Last updated: 2026-10-24. For the latest, check `docs/quickstart.md` and `docs/hackathon-demo.md`._
