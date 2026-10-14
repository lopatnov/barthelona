---
name: handoff
description: Session continuity for Claude Code and Codex. `write` (default) adds a docs/devlog entry and, if work is mid-flight, prints a paste-ready message for the next session. `resume` checks before the first edit that handed-over work is still needed and the tree matches. Use at the end of a session that changed files or decisions, and when asked to continue after a usage-limit reset, a pasted handoff or a long gap.
argument-hint: "[write|resume] [note | task path]"
arguments: [mode, note]
---
# Handoff (`$mode`, default `write`)

Get every fact from a command, never from memory. Run Python through the wrapper (`.\scripts\dev.ps1 <cmd>` or `scripts/dev.sh <cmd>`). Never include secret values, `.env` content or absolute paths under the user profile.

## write

1. **State.** `git rev-parse --abbrev-ref HEAD`, `git status --porcelain`, `git log --oneline -5`, `python scripts/sync_agent_configs.py --check`, `python scripts/deps_fingerprint.py --check`, and the last `verify` result (rerun `unit` if code changed since). WSL: `wsl.exe -l --running -q` (never boot it). List background shells, containers and staging dirs (`~/.cache/barthelona/devcheck/<name>/`) this session started: stop them, or hand them over.
2. **Mini-retro.** Name the friction: repeated workarounds, wrong assumptions (e.g. a planned module treated as existing), unclear or contradictory guidance, guard false positives or negatives, stale docs. Apply AGENTS.md "Lessons land where they act": small fixes now; anything touching invariants, permissions or hooks is proposed to the owner.
3. **Decisions.** Map each decision made in chat to an ADR (`new-adr`, or an `Amended by` line) or a roadmap open decision. An unmapped decision goes under Next.
4. **Devlog entry.** Insert at the top of the newest `docs/devlog/YYYY-Qn.md`, below its header; create the quarter's file if it is missing. Skip the entry if the session changed nothing. At most 12 lines, ASCII separators:
   ```markdown
   ## YYYY-MM-DD - claude|codex - <roadmap phase / deliverable>
   - Done: 1-3 bullets with paths; commit SHAs if committed, else "uncommitted: N paths".
   - Decided: D-NNN | open decision #N | none.
   - Learned: <lesson> -> <where it was recorded> | none.
   - Deferred: F-N rows added to docs/roadmap.md Follow-ups | none.
   - Verify: <one line: ruff, format, mypy, pytest counts>.
   - Next: <one concrete first action: a command or a file>.
   ```
   New-file header: `# Devlog YYYY-Qn` and one line: "Session history for Claude Code and Codex, newest first. Not authoritative (code, docs/architecture.md, docs/adr and docs/roadmap.md are). Never copy entries into AGENTS.md or CLAUDE.md; correct an old entry only by appending `Correction (date): ...`."
5. **Continuation message**, only if work is mid-flight. Print it addressed to the next session ("you"), without restating AGENTS.md:
   - the goal in one paragraph;
   - exact state: branch, uncommitted paths grouped by purpose and whether each is verified, roadmap item, ADRs touched and their status, generated files to refresh (Codex mirror, locks);
   - environment: lock freshness, WSL and docker images, LM Studio loaded model and context length;
   - quirks found, and where each was recorded;
   - owner actions pending (roadmap open decision #, `.wslconfig`, model downloads, `sudo` steps);
   - the next step as one literal command or file;
   - for a Codex successor: Claude hooks do not run there, so it runs `ruff format`, keeps LF in shell and assembly files, and runs `python scripts/sync_agent_configs.py` itself.
6. Commit the devlog entry as its own `docs` commit. Show the devlog diff.

## resume

Run before the first edit of handed-over work (a pasted handoff, a task chip, Codex work, "continue" after a usage-limit reset or a long gap). Task: `$note`.

1. **Tree.** `git status --porcelain`, `git log --oneline -15`, `git worktree list`; compare with the handoff or the newest devlog entry. Paths it lists as changed that are now clean or different mean another session committed, reverted or edited them: stop and report.
2. **Already done?** `git log --oneline -- <path>`; grep for the module or symbol; the roadmap tick and Follow-ups row; `docs/adr/README.md` for an ADR on the same topic or a D-number taken since the handoff.
3. **Someone else on it?** Files changed recently that this session did not touch may belong to a concurrent Claude Code or Codex session. Do not edit them without asking the owner.
4. **Environment drift.** If the task needs WSL, docker or LM Studio, run `env-doctor`: the VM may have stopped or the model may be unloaded.
5. **Decide.** Done: say so with the evidence and stop. Partly done: list what exists and what remains, and confirm the scope. Still needed: continue.
