# barthelona

A local-first agentic system that creates or edits **multi-file assembly projects** from a natural-language request.

## Table of Contents

- [Overview](#overview)
- [Status](#status)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
  - [Guides & References](#guides--references)
  - [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs)
  - [Configuration & Source Code](#configuration--source-code)
- [Integration Guides](#integration-guides)
  - [Meterless (Nightshift) Guide](#meterless-nightshift-guide)
  - [Zetaris Guide](#zetaris-guide)
  - [Hackathon Demo Guide](#hackathon-demo-guide)
- [Demo](#demo)
- [License](#license)

## Overview

Assembly is the first target family of a wider aim ([D-050](docs/adr/D-050-oracle-driven-builder-assembly-first-then-more-target-families.md)): an oracle-driven software builder. C applications, then web and 2D, are planned as roadmap Phase 6, after the assembler pipeline works end to end. The engine runs on Linux or Windows, and models can be served from several PCs ([D-049](docs/adr/D-049-linux-capable-engine-and-model-endpoints-across-pcs.md)).

You choose an assembler dialect (NASM and GNU as first; FASM, MASM-compatible and others later) and a target (architecture, OS, ABI, output format). You choose whether to create a new project or change an existing one, and describe the goal in English, Russian or Ukrainian. The system then:

1. turns the request into a spec, interface contracts and tests that you approve;
2. runs **Meta-Agentic Scrum** sprints. For each unit of work, the AI composes a bounded loop graph from tested building blocks (code, assemble, link, emulate, review, research, ask the human), and re-plans when it gets stuck;
3. accepts code only when real tools agree: the assembler, linker, symbol and ABI checks, the Unicorn emulator, and sandboxed tests in Docker;
4. delivers a self-contained git repository that builds without barthelona.

Models are pluggable:

- a local model in LM Studio (or Ollama) is always available;
- Anthropic, OpenAI, Google Gemini and DeepSeek are optional accelerators, configured in [`config/models.yaml`](config/models.yaml);
- dollar budgets are optional (spending is always metered; time and token limits always apply), and provider outages or empty balances fall back automatically to the next model, ending with the local one.

## Status

**Barthelona cannot create or edit projects yet.** The agent engine (the Meta-Agentic Scrum loop, the UI and the model-driven pipeline) does not exist; the description above is the design, not today's behavior.

- **Current phase:** Phase 0, foundations and the deterministic spine (last updated 2026-10-24). **Done:** design docs, agent configuration, environment scripts, domain models, the SQLite store, executors (Fake/WSL/Local/Sandbox), NASM/GAS adapters, the verification ladder V0–V2/V5/V6 ([`python -m barthelona verify`](src/barthelona/cli/verify.py)), the model gateway with fallback chains, the bench library, the ABI mutation corpus, Meterless (Nightshift) and Zetaris integrations, Markovian chunked runs, opt-in training data collection. **Still open:** the bake-off and local-model choice, Docker image digests in [`config/toolchains.lock.json`](config/toolchains.lock.json), and the Phase 0 review. Next is Phase 1 (an end-to-end run from the UI).
- **What you can try today:** the CLI ([`python -m barthelona version | schema | probe | verify | training status | chunked | meterless | zetaris`](src/barthelona/cli/)), two hand-written 3-module test projects that pass the full MVP ladder. **Detailed guide:** [`docs/current-status.md`](docs/current-status.md). The goal is code that is **correct**, as the oracles decide; today the demo path checks only that it assembles, not that it behaves.
- **Demo caveat:** `demos/simplest-demo` is a **placeholder, not a valid demo**. Claude wrote its sources, contract and test generators by hand because the engine does not exist yet; Barthelona only verifies it. Its scoring method is not documented, so its correctness is unproven. Real demos must be produced by Barthelona (mostly with local models) from a human-style prompt.
- **Where to look:** phases and exit criteria in [`docs/roadmap.md`](docs/roadmap.md) (its "Current status" line is the source of truth). When a phase changes, update this section and that line together.

## Quick Start

### Windows (PowerShell)

```powershell
.\scripts\create_env.ps1        # conda env 'barthelona' (Python 3.13) + hash-locked dependencies
. .\scripts\activate.ps1        # note the leading dot
.\scripts\doctor.ps1            # environment health check
copy .env.example .env          # optional: add cloud API keys
```

### Git Bash / Linux

```bash
scripts/create_env.sh
source scripts/activate.sh
scripts/doctor.sh               # or .\scripts\doctor.ps1 -StartWsl on Windows
cp .env.example .env            # optional: add cloud API keys
```

WSL2 (Ubuntu 26.04) and Docker are used for building and sandboxed testing. Full setup guide: [`docs/runbook.md`](docs/runbook.md).

### Requirements at a Glance

| Component                        | Windows                             | Linux                                |
| -------------------------------- | ----------------------------------- | ------------------------------------ |
| Python                           | 3.13 (conda)                        | 3.13 (conda)                         |
| Docker                           | WSL2 Ubuntu 26.04                   | Native Docker                        |
| WSL                              | Ubuntu 26.04 distro                 | N/A                                  |
| LM Studio                        | `http://127.0.0.1:1234/v1`          | `http://127.0.0.1:1234/v1` or remote |
| Optional: Meterless (Nightshift) | `http://127.0.0.1:8088/v1`          | Optional                             |
| Optional: Zetaris                | `http://localhost:8888/api/v1.0`    | Optional                             |
| Optional: Qdrant (project)       | `docker/qdrant/compose.yaml` in WSL | Same compose                         |

See [`docs/runbook.md`](docs/runbook.md) for detailed installation, WSL configuration (`.wslconfig`), and troubleshooting.

## Documentation

### Guides & References

- **[`docs/current-status.md`](docs/current-status.md)** — **Comprehensive technical reference** (actual runnable capabilities): detailed CLI commands, verification ladder V0–V8, model gateway, Meterless/Zetaris integration, chunked runs, training data, test projects, code generation, what doesn't work yet, directory layout, next steps for contributors
- **[`docs/quickstart.md`](docs/quickstart.md)** — **Concise getting-started guide**: installation, running the hello demo, creating your own assembly program, troubleshooting, known limits
- **[`docs/meterless-guide.md`](docs/meterless-guide.md)** — **Complete Meterless/Nightshift guide**: installation, Nightshift UI setup, lane configuration, profiles, H-MEM, troubleshooting
- **[`docs/zetaris-guide.md`](docs/zetaris-guide.md)** — **Complete Zetaris guide**: installation, API key setup, SQL queries, `--facts-sql` injection, fact registration, troubleshooting
- **[`docs/hackathon-demo-guide.md`](docs/hackathon-demo-guide.md)** — **Hackathon demo guide**: complete 3-layer setup (Zetaris, Cursor, Meterless/Nemotron), demo scenarios, troubleshooting
- **[`docs/architecture.md`](docs/architecture.md)** — The design: Scrum mapping, AI-composed sprint graphs, verification ladder, sandbox, knowledge, model routing and resilience, UI
- **[`docs/roadmap.md`](docs/roadmap.md)** — Phases, exit criteria, open decisions
- **[`docs/runbook.md`](docs/runbook.md)** — Environment setup and troubleshooting
- **[`docs/knowledge-sources.md`](docs/knowledge-sources.md)** — Assembler documentation sources and licenses
- **[`docs/requirements.md`](docs/requirements.md)** — Requirements and ambitions for future target families
- **[`docs/hackathon-demo.md`](docs/hackathon-demo.md)** — Hackathon demo design notes

### Architecture Decision Records (ADRs)

The [`docs/adr/`](docs/adr/) directory contains all architecture decisions (D-001 through D-056). Key decisions:

- **D-001** — [Meta-Agentic Scrum is the organizing model](docs/adr/D-001-meta-agentic-scrum-is-the-organizing-model.md)
- **D-006** — [Engine runs on Windows, toolchains run in pinned containers](docs/adr/D-006-engine-runs-on-windows-toolchains-run-in-pinned.md)
- **D-007** — [The verification ladder is the judge definition](docs/adr/D-007-the-verification-ladder-is-the-judge-definition.md)
- **D-008** — [The contract registry is the single source of truth](docs/adr/D-008-the-contract-registry-is-the-single-source-of.md)
- **D-010** — [Sandbox execution policy](docs/adr/D-010-sandbox-execution-policy.md)
- **D-021** — [MVP scope: NASM and GAS on x86-64 Linux ELF64](docs/adr/D-021-mvp-scope-nasm-and-gas-on-x86-64-linux-elf64.md)
- **D-029** — [Multi-provider model catalog](docs/adr/D-029-multi-provider-model-catalog.md)
- **D-030** — [Provider resilience and optional budgets](docs/adr/D-030-provider-resilience-and-optional-budgets.md)
- **D-031** — [Dependencies in pyproject, locked per platform](docs/adr/D-031-dependencies-in-pyproject-locked-per-platform.md)
- **D-034** — [Project-owned Qdrant in docker-compose](docs/adr/D-034-project-owned-qdrant-in-docker-compose.md)
- **D-036** — [Opt-in local training data collection](docs/adr/D-036-opt-in-local-training-data-collection.md)
- **D-049** — [Linux-capable engine and model endpoints across PCs](docs/adr/D-049-linux-capable-engine-and-model-endpoints-across-pcs.md)
- **D-050** — [Oracle-driven builder: assembly first, then more target families](docs/adr/D-050-oracle-driven-builder-assembly-first-then-more-target-families.md)
- **D-056** — [V3/V4 emulator implementation approach](docs/adr/D-056-v3-v4-emulator-implementation-approach.md)

### Configuration & Source Code

- **[`AGENTS.md`](AGENTS.md)**, **[`CLAUDE.md`](CLAUDE.md)**, **[`.claude/`](.claude/)** — Instructions and configuration for coding agents (Claude Code; Codex via a generated mirror)
- **[`config/models.yaml`](config/models.yaml)** — Model catalog, role chains, budgets, resilience
- **[`src/barthelona/`](src/barthelona/)** — Source code: CLI, domain, executors, toolchains, verification, contracts, LLM gateway, persistence, training

## Integration Guides

### Meterless (Nightshift) Guide

[`docs/meterless-guide.md`](docs/meterless-guide.md) — Complete step-by-step guide for Meterless Nightshift:

- **Installation & Nightshift UI setup** — download, providers, lanes, runtime token
- **Barthelona configuration** — `config/models.yaml` provider/models/role chains explained
- **Profiles & role chains** — `meterless`, `local-only`, `hybrid`, `cloud`; when to use each
- **Running tasks** — `chunked run` flags, `--assemble`, `--repair`, `--expect-stdout`, `--memory`, `--plan-role`
- **H-MEM memory** — how recall/write works, running the memory proof (demos/hello)
- **Troubleshooting** — unauthorized, unavailable, fallback to local, lane warnings, thinking budget
- **Advanced** — LAN deployment, custom models, timeouts, disabling thinking

### Zetaris Guide

[`docs/zetaris-guide.md`](docs/zetaris-guide.md) — Complete step-by-step guide for Zetaris:

- **Installation** — Docker, existing instance
- **Setup** — API key creation, connection details
- **Barthelona configuration** — `.env` variables
- **Verification** — `zetaris status`, `zetaris sql` test queries
- **Using with `chunked run`** — `--facts-sql` injection, how facts enter chunk 1
- **Registering assembler facts** — intended schema, manual registration, future automation
- **Troubleshooting** — unauthorized, offline, unconfigured, query errors, injection guard
- **Advanced** — combining with H-MEM, different profiles, programmatic Python access

### Hackathon Demo Guide

[`docs/hackathon-demo-guide.md`](docs/hackathon-demo-guide.md) — Complete hackathon preparation guide:

- **Layer 1 (DATA)**: Zetaris setup, API key, fact registration (syscalls, instructions)
- **Layer 2 (BUILD)**: Cursor + Barthelona env, `verify`, Markovian/H-MEM engines
- **Layer 3 (POWER)**: Nightshift install, NVIDIA provider, Race+Judge lanes, LM Studio fallback
- **Integration verification**: 7-step smoke test across all layers
- **Demo scenarios**: Memory proof (hello), Multi-chunk (fizzbuzz), Zetaris injection
- **Troubleshooting**: Per-layer common issues with fixes
- **Quick reference card**: One-time setup, daily start, demo commands

## Demo

[`demos/simplest-demo`](demos/simplest-demo) is a git submodule ([barthelona-simplest-demo](https://github.com/lopatnov/barthelona-simplest-demo)): an interactive console temperament questionnaire (Russian interface) in four NASM modules that passes barthelona's verification ladder (tamper gate, V0-V2, V5, V6) in its own CI. It is a hand-written placeholder (see the caveat above): its README says which parts the pipeline did and which Claude wrote by hand because the engine does not exist yet. Clone with `git clone --recurse-submodules`, or run `git submodule update --init` afterwards.

Additional demo projects (each has its own README with run instructions):

- [`demos/hello/`](demos/hello/) — hello world demo proving memory recall (H-MEM) across runs; run with `--profile meterless`
- [`demos/fizzbuzz/`](demos/fizzbuzz/) — fizzbuzz demo needing multiple chunks; run with `--profile local-coder` (requires LM Studio with Qwen coder + Codestral)

See [`docs/hackathon-demo.md`](docs/hackathon-demo.md) for design notes on the demo path.

## License

BSD 2-Clause, see [`LICENSE`](LICENSE). Authorship, attribution and third-party material: [`NOTICE.md`](NOTICE.md).
