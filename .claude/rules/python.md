---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---
# Python conventions (barthelona)

- Python 3.13, full type hints, `mypy --strict` clean, `ruff check` / `ruff format` clean (config in `pyproject.toml`).
- Pydantic v2 models live in `src/barthelona/domain/`. That package does no I/O; it holds data models and pure validation only.
- Use `async` in `engine/` and `nodes/`. Never block the event loop with `subprocess.run`; use the executor layer.
- `subprocess` takes argv lists only, never `shell=True`. Use `pathlib`. Open text files with `encoding="utf-8", newline="\n"`.
- No `print` in library code: emit `RunEvent`s or use `logging`. Never log secrets, prompts containing keys, or `.env` content.
- Import layering (an import-linter test will enforce it):
  - `domain` ← {contracts, toolchains, executors, verification, knowledge, memory, llm, prompting, persistence, workspace, policy} ← `nodes` ← `engine` ← `cli`;
  - `ui` imports only `domain`, `persistence` and `config`.
- Tests:
  - pytest markers `wsl` (needs WSL/docker), `llm` (real model calls) and `slow`. The default run excludes them.
  - Use `FakeGateway` / `FakeExecutor` for engine and graph tests.
  - Use Hypothesis for parsers and validators.
- Do not add dependencies ad hoc: edit `pyproject.toml`, run `scripts/lock.ps1`, then `scripts/create_env.ps1`. Never add LiteLLM, PyMuPDF or GPUtil.
