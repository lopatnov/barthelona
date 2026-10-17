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

**Status:** Phase 0 in progress: repository and environment done, code skeleton not started. See `docs/roadmap.md`.

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

## License

BSD 2-Clause, see `LICENSE`. Authorship, attribution and third-party material: `NOTICE.md`.
