# barthelona

A local-first agentic system that creates or edits **multi-file assembly projects** from a natural-language request.

Assembly is the first target family of a wider aim (D-050): an oracle-driven software builder. C applications, then web and 2D, are planned as roadmap Phase 6, after the assembler pipeline works end to end. The engine runs on Linux or Windows, and models can be served from several PCs (D-049).

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
- **What you can try today:** generate NASM code through Meterless Nightshift in chunks, check it with NASM and keep what a passing run learned (`chunked run --assemble`), plus the CLI (`version | schema | probe | verify | training status | meterless | zetaris`). What works, what to install and how to run it: `docs/getting-started.md`.
- **Demo caveat:** `demos/simplest-demo` is a **placeholder, not a valid demo**. Claude wrote its sources, contract and test generators by hand because the engine does not exist yet; Barthelona only verifies it. Its scoring method is not documented, so its correctness is unproven. Real demos must be produced by Barthelona (mostly with local models) from a human-style prompt.
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
| `docs/getting-started.md` | What works today, what to install, how to run the memory demo, known limits |
| `docs/architecture.md` | The design: Scrum mapping, AI-composed sprint graphs, verification ladder, sandbox, knowledge, model routing and resilience, UI |
| `docs/adr/` | Architecture decision records D-001 to D-035 |
| `docs/roadmap.md` | Phases, exit criteria, open decisions |
| `docs/runbook.md` | Environment setup and troubleshooting |
| `docs/knowledge-sources.md` | Assembler documentation sources and licenses |
| `AGENTS.md`, `CLAUDE.md`, `.claude/` | Instructions and configuration for coding agents (Claude Code; Codex via a generated mirror) |

## Demo

`demos/simplest-demo` is a git submodule ([barthelona-simplest-demo](https://github.com/lopatnov/barthelona-simplest-demo)): an interactive console temperament questionnaire (Russian interface) in four NASM modules that passes barthelona's verification ladder (tamper gate, V0-V2, V5, V6) in its own CI. It is a hand-written placeholder (see the caveat above): its README says which parts the pipeline did and which Claude wrote by hand because the engine does not exist yet. Clone with `git clone --recurse-submodules`, or run `git submodule update --init` afterwards.

## License

BSD 2-Clause, see `LICENSE`. Authorship, attribution and third-party material: `NOTICE.md`.
