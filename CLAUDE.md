@AGENTS.md

# Claude Code specifics

The shared instructions above (`AGENTS.md`) are also read by Codex. Put shared rules there; keep this file for Claude Code only.

- **Skills and subagents** are routed by the "Who to call" table in `AGENTS.md`. `/new-adr`, `/add-dialect` and `/add-node-type` are manual (`disable-model-invocation`); the reviewers are tool-restricted to read-only. After editing `.claude/skills/` or `.claude/agents/`, the PostToolUse hook regenerates the Codex mirror; a guard hook blocks direct edits to `.agents/` and `.codex/agents/`.
- **Path-scoped rules** in `.claude/rules/` load when you touch matching files (Python, engine, LLM gateway, UI, toolchains, verification, knowledge, assembly sources, scripts, docs, agent config).
- **Tools in agent shells:** each Bash/PowerShell call starts fresh without the conda env. Use `.\scripts\dev.ps1 <cmd>` / `scripts/dev.sh <cmd>`; these are pre-approved in `settings.json` for ruff, mypy, pytest and the check scripts.
- **Shell pitfalls on this host** (more symptoms in `docs/runbook.md` §8):
  - Create or patch files with Edit/Write, not heredocs, `sed -i` or `python -c`, when the text has backslashes or quotes (assembly, regexes, Windows paths); re-read the result.
  - Git Bash rewrites POSIX-looking arguments for native programs (`wsl.exe`, `docker.exe`, `cmd`): `/c/x:/work` arrives as `C:\x;C:\Program Files\Git\work`. Pass Linux commands as one quoted `bash -lc '...'` string, prefix `MSYS_NO_PATHCONV=1`, or use the PowerShell tool.
  - Check exit status before counting or parsing piped output: an error piped into `wc -l` counts as one line.
- **Hooks** (`.claude/hooks/README.md`): guards for destructive shell commands and protected paths (`git push` asks; force-push is blocked); `ruff format` plus a lint report after Python edits; LF enforcement for shell and assembly files; a session status at startup. After changing a hook, run `powershell -NoProfile -ExecutionPolicy Bypass -File .claude\hooks\test-hooks.ps1`.
- Before touching Claude API code in the product (`src/barthelona/llm/anthropic_backend.py`), use the `/claude-api` skill.
- Personal, uncommitted notes go in `CLAUDE.local.md` (gitignored). Personal settings go in `.claude/settings.local.json` (gitignored).
