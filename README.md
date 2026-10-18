# barthelona

A local-first agentic system that creates or edits **multi-file assembly projects** from a natural-language request.

You choose an assembler dialect (NASM and GNU as first; FASM, MASM-compatible and others later) and a target (architecture, OS, ABI, output format). You choose whether to create a new project or change an existing one, and describe the goal in English, Russian or Ukrainian. The system then:

1. turns the request into a spec, interface contracts and tests that you approve;
2. runs **Meta-Agentic Scrum** sprints. For each unit of work, the AI composes a bounded loop graph from tested building blocks (code, assemble, link, emulate, review, research, ask the human), and re-plans when it gets stuck;
3. accepts code only when real tools agree: the assembler, linker, symbol and ABI checks, the Unicorn emulator, and sandboxed tests in Docker;
4. delivers a self-contained git repository that builds without barthelona.

Models are pluggable:
- a local model in LM Studio (or Ollama) is always available;
- Anthropic, OpenAI, Google Gemini and DeepSeek are optional accelerators, configured in `config/models.yaml`;
- dollar budgets are optional (spending is always metered; time and token limits always apply), and provider outages or empty balances fall back automatically to the next model, ending with the local one.

## Status: not ready yet

**Barthelona cannot create or edit projects yet.** The agent engine (the Meta-Agentic Scrum loop, the UI and the model-driven pipeline) does not exist; the description above is the design, not today's behavior.

- **Current phase:** Phase 0, foundations and the deterministic spine (last updated 2026-10-18). Done: design docs, agent configuration, environment scripts, domain models, the SQLite store, executors, NASM/GAS adapters, the verification ladder (`python -m barthelona verify`), the model gateway, the bench library and the ABI mutation corpus. Still open: the bake-off and local-model choice, Docker image digests, and the Phase 0 review. Next is Phase 1 (an end-to-end run from the UI).
- **What you can try today:** the CLI (`python -m barthelona version | schema | probe | verify | training status`) and the demo below.
- **Demo caveat:** `demos/simplest-demo` was written by hand by Claude, because the engine does not exist yet. Barthelona's verification ladder checks it; barthelona did not generate it.
- **Where to look:** phases and exit criteria in `docs/roadmap.md` (its "Current status" line is the source of truth). When a phase changes, update this section and that line together.

## Quick start (Windows, PowerShell)

```powershell
.\scripts\create_env.ps1        # conda env 'barthelona' (Python 3.13) + hash-locked dependencies
. .\scripts\activate.ps1        # note the leading dot
.\scripts\doctor.ps1            # environment health check
copy .env.example .env          # optional: add cloud API keys
```

Git Bash: `scripts/create_env.sh`, then `source scripts/activate.sh`. WSL2 (Ubuntu) and Docker are used for building and sandboxed testing. Full setup: `docs/runbook.md`.

## Documentation

| Document | Contents |
| --- | --- |
| `docs/architecture.md` | The design: Scrum mapping, AI-composed sprint graphs, verification ladder, sandbox, knowledge, model routing and resilience, UI |
| `docs/adr/` | Architecture decision records D-001 to D-035 |
| `docs/roadmap.md` | Phases, exit criteria, open decisions |
| `docs/runbook.md` | Environment setup and troubleshooting |
| `docs/knowledge-sources.md` | Assembler documentation sources and licenses |
| `AGENTS.md`, `CLAUDE.md`, `.claude/` | Instructions and configuration for coding agents (Claude Code; Codex via a generated mirror) |

## Demo

`demos/simplest-demo` is a git submodule ([barthelona-simplest-demo](https://github.com/lopatnov/barthelona-simplest-demo)): a Snake game in four NASM modules that passes barthelona's verification ladder (tamper gate, V0-V2, V5, V6) in its own CI. Its README says which parts the pipeline did and which Claude wrote by hand because the engine does not exist yet. Clone with `git clone --recurse-submodules`, or run `git submodule update --init` afterwards.

## License

BSD 2-Clause, see `LICENSE`. Authorship, attribution and third-party material: `NOTICE.md`.
