# D-033: Development-process conventions for coding agents (adapted from the owner's conduit project)

- Status: Proposed
- Date: 2026-10-13
- Amends: D-026, D-032
- Amended by: D-035

## Context

The owner's other project, conduit (a mature Rust codebase), accumulated agent-configuration practices over months, each added after a real failure. These include:

- a security review that ran only when the agent judged it necessary, which is exactly what an injection would steer;
- deferrals that lived only in chat and were lost;
- a shell lesson written into a log seven times before it became a rule;
- a subagent that went looking for credentials when a tool was missing;
- always-loaded instructions that grew to 207 KB before a forced diet;
- handed-over work that had already been merged by the time the next session started.

barthelona has the same exposures. Claude Code and Codex share one checkout, cloud keys sit in `.env`, the shell timeout is 30 minutes, and `.reference/` holds third-party agent repos with their own instruction files. A five-reader review of conduit's configuration, followed by a synthesis checked against barthelona's existing setup, selected what transfers.

## Decision

1. **AGENTS.md process rules** (shared with Codex):
   - an explicit priority order when goals conflict;
   - research prior art before building;
   - "Done" includes a verify checklist and a "Found while here" list;
   - deferred items go to `docs/roadmap.md` Follow-ups;
   - findings are fixed at the cause;
   - lessons land where they act (hook, rule, skill or runbook);
   - respect other sessions' changes;
   - no credential hunting or prompting commands on tool gaps;
   - conventional commit messages with explicit staging.
2. **"Who to call" table** in AGENTS.md routes every skill and agent. The main session conducts, and agents never call agents.
3. **Unconditional review gate:**
   - **Trigger:** `architecture-guardian` runs before any commit whose staged diff touches gated paths (engine-side code with I/O, docker, policies, the model catalog, scripts, `pyproject.toml`, and the agent configuration itself).
   - **Verdict:** it is tied to the staged-diff hash; a changed diff needs a delta review.
   - **Untrusted text:** claims of prior approval inside reviewed content are findings, never acted on.
4. **`handoff` skill** (`write` / `resume`) with a lean `docs/devlog/YYYY-Qn.md`:
   - each entry is at most 12 lines, links instead of retelling, and is never copied into instruction files;
   - the SessionStart hook prints the newest entry's "Next" line.
5. **Agent-config hygiene** (`.claude/rules/agent-config.md` + `tests/unit/test_agent_config.py`):
   - an instruction budget, `AGENTS.md` + `CLAUDE.md` ≤ 200 lines and 22 KB;
   - rules must be path-scoped and ≤ 5 KB;
   - skill and agent frontmatter is checked, including that read-only agents say so in the body (Codex sees only the body);
   - every skill and agent must appear in the routing table.
6. **The verify skill gains a done checklist** with negative controls (a regression test must be seen failing on the unfixed code), re-reading after scripted edits, docs, roadmap, gate and Found-while-here items.
7. **`docs-researcher`** reads the installed lock-pinned source first for library behavior, and has a prior-art mode over `.reference/` that treats that material as untrusted.
8. **Windows shell pitfalls** go in `CLAUDE.md`, and their symptoms in `docs/runbook.md` §8.
9. **Deferred until their triggers**, recorded in `docs/roadmap.md` Parked ideas: verify-runner, bench-runner, security-reviewer, integrity-auditor, license-reviewer, testing and cleanup skills, generated Codex hooks, extra guard patterns, and others.

Prior art:
- conduit `.claude/rules/workflow.md` and `conventions.md` (2026-09/10): process rules and their dated owner decisions;
- conduit `.claude/agents/*` (contract shape: mandate, boundaries, outputs, escalation) and `commands/handoff.md`, `verify-handed-over-task.md`;
- conduit `.claude/logs/session-rotation.md` and the 2026-10-03 instruction diet (#512): what not to copy (session rotation, journal summaries in CLAUDE.md, a 388 KB log).

## Rationale

These rules came from observed failures, not speculation, and each is small. The gate and the budget are enforced mechanically (path trigger, test), because conduit showed that judgment-based gates and unenforced budgets erode.

## Alternatives considered

- **Copy conduit's agent roster wholesale** (16 agents): too much for a pre-Phase-0 repo. Most roles are parked with explicit triggers.
- **Keep instructions in `CLAUDE.md` only, with AGENTS.md as a pointer (conduit's choice):** rejected by D-032; the shared file serves Codex too.
- **A journal inside instruction files:** rejected; conduit's summaries drifted and had to be removed.

## Consequences

- Commits that touch the agent configuration or scripts need an `architecture-guardian` run first. This costs one reviewer call per commit.
- The instruction budget test fails when `AGENTS.md` grows too large; detail must move to skills, scoped rules or `docs/`.
