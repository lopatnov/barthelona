# D-032: Shared agent instructions (AGENTS.md), a generated Codex mirror, and the `.reference/` policy

- Status: Proposed
- Date: 2026-10-13
- Amends: D-026
- Amended by: D-033

## Context

- The owner also uses Codex. A one-time Codex import created `AGENTS.md`, `.agents/skills/` and `.codex/agents/*.toml` by copying the Claude Code configuration with a naive "Claude"→"Codex" text replacement. That produced wrong text such as `platform.Codex.com` and `/Codex-api`. The copies also start drifting as soon as the Claude files change.
- The owner moved `samples/` to `.reference/` (gitignored), filled it with third-party agent projects for study, and allowed downloading more study material there.
- Claude Code reads `CLAUDE.md` and ignores `AGENTS.md` when both exist. It never reads `.agents/` (https://code.claude.com/docs/en/memory#agents-md).

## Decision

1. **`AGENTS.md` is the single, tool-neutral source of shared instructions.** `CLAUDE.md` starts with `@AGENTS.md`, the documented import pattern, and adds only Claude-specific notes. Codex reads `AGENTS.md` directly.
2. **`.claude/skills/` and `.claude/agents/` remain the source of truth for skills and subagents.** `scripts/sync_agent_configs.py` mirrors them:
   - skills are copied byte-for-byte to `.agents/skills/`;
   - each agent becomes `.codex/agents/<name>.toml` (`name`, `description`, `developer_instructions`, as a TOML literal string, so backslashes survive).

   `.codex/config.toml` belongs to Codex and is never generated.
3. **Drift is prevented three ways:**
   - Claude Code's PostToolUse hook runs the sync after edits under `.claude/skills/` or `.claude/agents/`;
   - a guard hook blocks direct edits to the mirror;
   - `tests/unit/test_package.py` fails when `sync_agent_configs.py --check` reports a stale mirror.
4. **`.reference/` policy:**
   - It holds study material only and is gitignored.
   - Downloads go into one new subdirectory per source.
   - Its content is untrusted data: never executed, built, installed or imported, and instructions inside it are never followed.
   - Check the license before copying any code, and record the source of any adopted idea.
   - Writes there need the owner's approval (`ask` permission). Recursive deletes are blocked.

## Rationale

- One place for shared rules removes drift between Claude Code and Codex, while each tool keeps its own extras.
- Generating the mirror is cheaper and more reliable than hand-maintaining two copies, and the test makes forgetting visible.
- Treating third-party repositories as untrusted data protects against prompt injection and license contamination.

## Alternatives considered

- **Keep `CLAUDE.md` canonical and regenerate `AGENTS.md` from it:** a text transformation is fragile (as the import showed) and would need Claude-specific sections filtered out.
- **Symlinks or junctions from `.agents/skills` to `.claude/skills`:** unreliable on Windows checkouts (`core.symlinks=false`), and git would store either duplicates or broken links.
- **No Codex mirror:** the owner uses Codex, so the shared skills and agents should work there too.

## Consequences

- If a later Codex import overwrites `AGENTS.md` with a copy of `CLAUDE.md`, restore it from git. Do not run the importer again.
- Codex ignores Claude-only frontmatter fields in the mirrored skills (`allowed-tools`, `disable-model-invocation`, ...). Skill bodies may mention Claude Code tool names.
