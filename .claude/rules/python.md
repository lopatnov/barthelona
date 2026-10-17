---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---
# Python conventions (barthelona)

- Python 3.13, full type hints, `mypy --strict` clean, `ruff check` / `ruff format` clean (config in `pyproject.toml`).
- Code quality follows the owner's chosen references (2026-10-14): Robert C. Martin (*Clean Code*, *Clean Architecture*), Luciano Ramalho (*Fluent Python*), Brett Slatkin (*Effective Python*) and Dan Bader (*Python Tricks*). In practice:
  - small functions that do one thing, at one level of abstraction; names from the domain, no abbreviations or flag arguments;
  - dependencies point inward (the layering below); side effects at the edges, pure logic in the core;
  - idiomatic Python over ported idioms: comprehensions, context managers, `enumerate`/`zip`/`itertools`, dataclasses or Pydantic over ad hoc dicts, `StrEnum` over string constants;
  - errors raise specific exceptions with a message that names the bad value; no bare `except`, no silent fallbacks (designed fallbacks emit an event with the reason);
  - a comment says why, not what; delete dead code instead of commenting it out.
- Size limits (AGENTS.md "Code size limits"): at most 400 code lines per file (warning above 250; comments, docstrings, blanks and tests excluded), and ruff's `C901`/`PLR0912`/`PLR0915` keep functions small. Split a growing module by responsibility before it hits the warning.
- Pydantic v2 models live in `src/barthelona/domain/`. That package does no I/O; it holds data models and pure validation only.
- Use `async` in `engine/` and `nodes/`. Never block the event loop with `subprocess.run`; use the executor layer.
- `subprocess` takes argv lists only, never `shell=True`. Use `pathlib`. Open text files with `encoding="utf-8", newline="\n"`.
- No `print` in library code: emit `RunEvent`s or use `logging`. Never log secrets, prompts containing keys, or `.env` content.
- Import layering (an import-linter test will enforce it):
  - `domain` ← {contracts, toolchains, executors, verification, knowledge, memory, llm, prompting, persistence, workspace, policy, training} ← `nodes` ← `engine` ← `cli`;
  - `ui` imports only `domain`, `persistence` and `config`.
- Tests:
  - pytest markers `wsl` (needs WSL/docker), `docker` (needs a running `bart-tc` container on any host; the CI `docker` job runs them), `llm` (real model calls) and `slow`. The default run excludes them.
  - Use `FakeGateway` / `FakeExecutor` for engine and graph tests.
  - Use Hypothesis for parsers and validators.
- Do not add dependencies ad hoc: edit `pyproject.toml`, run `scripts/lock.ps1`, then `scripts/create_env.ps1`. Never add LiteLLM, PyMuPDF or GPUtil.
