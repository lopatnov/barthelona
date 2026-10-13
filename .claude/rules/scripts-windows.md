---
paths:
  - "scripts/**"
  - ".claude/hooks/**"
  - "**/*.ps1"
---
# Windows / shell scripts rules

- PowerShell scripts must work in Windows PowerShell 5.1 AND PowerShell 7:
  - no `&&`/`||` pipeline chains, ternaries or `??`;
  - ASCII-only content (5.1 reads BOM-less UTF-8 as ANSI);
  - `.ps1` files are CRLF (`.gitattributes`).
- Use `$ErrorActionPreference = 'Stop'` and `Set-StrictMode -Version Latest` in standalone scripts. Never use them in dot-sourced scripts (`activate.ps1`), because they would leak into the user's session.
- After calling a native executable, check `$LASTEXITCODE`.
- Make no machine-wide changes (execution policy, PATH, registry, `conda init`, `.wslconfig`). Document them as owner actions in `docs/runbook.md`.
- Bash scripts:
  - LF line endings;
  - `set -euo pipefail` in executed scripts, not in sourced ones;
  - must work in Git Bash (MINGW) and Linux.
- Never print secrets. `.env` is parsed (`KEY=VALUE`), never executed or sourced.
- Hook scripts (`.claude/hooks/`):
  - must stay fast (well under 1 s), read their JSON from stdin, and never block on unreadable input;
  - block only with exit code 2 plus a clear reason on stderr;
  - after any change, re-run the hook test harness described in `.claude/hooks/README.md`.
