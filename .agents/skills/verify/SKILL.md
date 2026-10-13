---
name: verify
description: Run barthelona's quality gates (ruff lint + format check, mypy --strict, pytest with the default marker selection, Codex-mirror and lock-fingerprint checks), summarize failures with file:line, then walk the done checklist (tests that can fail, docs, roadmap, review gate, Found while here). Use after code changes and before declaring a task done.
argument-hint: "[unit|wsl|all] [path]"
arguments: [scope, path]
allowed-tools: PowerShell(.\scripts\dev.ps1 ruff *), PowerShell(.\scripts\dev.ps1 mypy*), PowerShell(.\scripts\dev.ps1 python -m pytest*), PowerShell(.\scripts\dev.ps1 python scripts/sync_agent_configs.py*), PowerShell(.\scripts\dev.ps1 python scripts/deps_fingerprint.py*), Bash(scripts/dev.sh ruff *), Bash(scripts/dev.sh mypy*), Bash(scripts/dev.sh python -m pytest*), Bash(scripts/dev.sh python scripts/sync_agent_configs.py*), Bash(scripts/dev.sh python scripts/deps_fingerprint.py*)
---
# Verify

Scope: `$scope` (default `unit`). Path: `$path` (default: whole repo).

Agent tool shells start without the conda env, so always run tools through the wrapper:
- PowerShell: `.\scripts\dev.ps1 <cmd>`
- Bash: `scripts/dev.sh <cmd>`

The wrapper puts the env on PATH for one command, without loading `.env`. Never dot-source `activate.ps1` in an agent shell: that would load the owner's API keys into it. If the wrapper reports that the env is missing, say so and stop; do not install anything.

Run these steps in order. Keep going even if one fails, then report:

1. `ruff check $path` (default `.`)
2. `ruff format --check $path`
3. `mypy` (configured in `pyproject.toml`: strict, `src/barthelona`)
4. `python scripts/sync_agent_configs.py --check` (the Codex mirror) and `python scripts/deps_fingerprint.py --check` (locks match `pyproject.toml`)
5. pytest:
   - `unit` (default): `python -m pytest -q`. The default `addopts` already exclude the `wsl`, `llm` and `slow` markers.
   - `wsl`: `python -m pytest -q -m wsl`. Needs the WSL VM and docker; say so if they are down.
   - `all`: `python -m pytest -q -m "wsl or llm or slow or not (wsl or llm or slow)"`. Warn first that `llm` tests may call paid cloud models.
   - Exit code 5 (no tests collected) means "no tests yet", not a failure.

Report:
- one line per step: pass / fail / skipped;
- failures grouped by root cause, with `file:line`;
- the smallest next fix.

## Done checklist

After the gates, mark each item done / n/a / open. Any open item means the task is not done yet; say what is missing.

- [ ] New behavior has tests at the right layer (FakeGateway/FakeExecutor, Hypothesis, captured diagnostics, goldens).
- [ ] Each regression test was seen failing on the unfixed code, and its fixture separates buggy from correct behavior (e.g. rsp misaligned by exactly 8; a callee-saved register clobbered on only one return path). Each new ABI check detects its bad corpus entry and passes its good one.
- [ ] After a scripted or bulk edit, or a `ruff format` reflow, the changed lines were re-read: a replace can silently match nothing.
- [ ] Docs match the change: `docs/architecture.md`, `docs/adr/README.md`, `docs/runbook.md`, `config/models.yaml`, and the AGENTS.md Commands table ("Available" column) and repo map.
- [ ] `docs/roadmap.md`: deliverables are ticked only with evidence (a test or a command); deferred items are added to Follow-ups.
- [ ] If hooks changed: `.claude/hooks/test-hooks.ps1` passed and `.claude/hooks/README.md` is updated.
- [ ] Review gate (AGENTS.md "Who to call"): when gated paths are staged, the `architecture-guardian` verdict and its staged-diff hash are noted.
- [ ] The "Found while here" list was shown to the owner, each item with a disposition.
- [ ] No other session's changes were reverted, reformatted or staged.

Do not edit code unless the user asked for fixes.
