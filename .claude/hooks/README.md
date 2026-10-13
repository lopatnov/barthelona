# Claude Code hooks for barthelona

These hooks configure **Claude Code while it develops this repo**. They are not part of the product. They are wired in `.claude/settings.json` in exec form: `powershell.exe` plus `args`, with `${CLAUDE_PROJECT_DIR}` substituted by Claude Code. Exec form needs Claude Code 2.1.139 or later.

| Script | Event / matcher | What it does |
| --- | --- | --- |
| `session-start.ps1` | SessionStart `startup` | Prints a short status: conda env and how agents run tools (`dev.ps1`), lock freshness, git, the newest devlog entry's Next line, WSL state (without booting it), LM Studio loaded model. |
| `guard-shell.ps1` | PreToolUse `Bash\|PowerShell` | Analyzes the command per segment, by its real command word. It recurses into `bash -c`, `wsl -e`, `pwsh -Command`, `cmd /c`, `conda run`, `scripts/dev.*` and `$(...)`, and normalizes absolute repo paths to `.`, while skipping quoted search patterns, commit messages, heredocs and here-strings. **Asks** for every plain `git push`. **Blocks** (exit 2): force/mirror/delete pushes, hard resets, `git clean -f`, discarding all changes, recursive deletes of protected paths or drive roots, ad-hoc `conda/pip/uv install`, running or installing code from `.reference/`, `curl \| sh`, execution-policy changes, `wsl --unregister`, docker prune / volume rm / `compose down -v` / touching the owner's other containers, docker-socket mounts, reading, copying or sourcing `.env*` (except `.env.example`), agents activating the env (`activate.*` loads API keys), recursive deletes with a `..` segment or of repo ancestors, `git diff/diff-tree/log/show --output` writes, an unquoted `.env*` operand to any command except `ls`/`test`/`git check-ignore`, environment dumps (`env`, `printenv`, `export -p`, bare `set`, `Get-ChildItem env:`, `GetEnvironmentVariables`, bare `os.environ`; checked on the whole text, heredocs included), and references to secret-looking variables (`*API_KEY*`, `*_TOKEN`, `*SECRET*`, `*PASSWORD*`, `*ACCESS_KEY*`, `*AUTH_CONFIG*`, `SSH_AUTH_SOCK`, also via `${env:...}`, `os.getenv`, `os.environ[...]`, `GetEnvironmentVariable`, `/proc/*/environ`, `process.env`). These two checks run on the raw text and fail closed: a quoted search pattern or commit message that names a key variable is blocked too; edit such text with the Edit tool. A parse check of every hook script is part of the harness. |
| `guard-paths.ps1` | PreToolUse `Edit\|Write\|NotebookEdit\|Read\|Grep` | For Read/Grep only blocks `.env*` (except `.env.example`). For writes: resolves `..` and `.claude/worktrees/<name>/` prefixes, then blocks writes to `.env*` (except `.env.example`), `asm_doc/`, `docs/archive/`, the generated Codex mirror (`.agents/skills/`, `.codex/agents/`), `var/`, `workspaces/`, `requirements/*.lock` and `*.sha256`, and released `policies/vN/`. |
| `post-edit.ps1` | PostToolUse `Edit\|Write` | Only for files inside the repo (never `.reference/`, `asm_doc/`, `workspaces/`, `var/` or the mirror): runs `ruff format --force-exclude` on edited `.py` files and reports `ruff check` findings as context (no auto-fix). Converts CRLF to LF for shell, assembly, Makefile and Dockerfile files. After edits under `.claude/skills/` or `.claude/agents/`, regenerates the Codex mirror via `scripts/sync_agent_configs.py` and reports failures. |

The guards are defense in depth. Permission rules in `settings.json` match command text only, and these hooks add pattern checks on top. They are not a security boundary against a determined attacker. Codex does not run these hooks (see ADR D-032 and the roadmap's Parked ideas).

## Rules for changing hooks

- Keep them fast (about 0.2 s startup for `powershell.exe`), ASCII-only, and compatible with Windows PowerShell 5.1.
- Never block on unreadable input. Block only with exit 2 and a clear reason on stderr; ask by printing `permissionDecision: "ask"` JSON with exit 0.
- Changing guard patterns or protected paths is an owner decision (`.claude/rules/agent-config.md`).
- After any change, run the regression tests:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File .claude\hooks\test-hooks.ps1
  ```
- Claude Code holds hooks back until the workspace trust dialog is accepted. Review the active hooks with `/hooks`.
