# D-035: Coding agents commit, push and merge their own PRs without owner approval

- Status: Proposed
- Date: 2026-10-13
- Amends: D-033

## Context

AGENTS.md (no earlier ADR) said agents commit and push only when the owner asks, and every `git push` stopped on an approval prompt (the `guard-shell.ps1` hook plus `ask` entries in `.claude/settings.json`). Commits, stash, checkout, switch, rebase and merge also prompted. Agents often work while the owner is away, so finished, reviewed and green work sat waiting for a click. On 2026-10-13 the owner asked to drop all of these approvals for commits, pushes and PRs.

## Decision

- Agents commit, push their feature branches and open PRs without asking.
- Agents merge their own PRs once the PR's checks have reported and pass, review threads are resolved, the review gate passed and `verify` passes on the PR head. The repo has no CI workflows yet, so the checks are the GitHub apps (CodeRabbit, SonarCloud, Socket); with no checks reported, the owner merges. This fails closed.
- No prompts for routine git: the hook's `ask` path is removed, and git `commit`, `push`, `add`, `stash`, `checkout`, `switch` and `merge` move from `ask` (or default) to `allow`. Other commands keep the default permission mode.
- New blocks replace prompts where work could be lost or the PR path skipped, in the hook (any argument order) and in `deny`: pushes to `main`/`master`, `git rebase`, `git commit --amend`, `git stash drop|clear`, `git checkout -f|--force`, `git switch -f|--force|--discard-changes`.
- PR merges go through the GitHub API, never `--delete-branch`: deleting remote branches stays forbidden.
- Unchanged: the review gate before gated commits; the blocks on force-push, `--mirror`, deleting remote branches, `git reset --hard`, `git clean -f` and discarding all changes; never committing secrets.

## Rationale

The checks that protect quality are the review gate, CI and review threads, not a prompt at push time. Destructive history operations stay blocked because they cannot be undone from a PR.

## Alternatives considered

- Drop only the push prompt: still leaves commits and merges waiting on the owner.
- Ask only for pushes to `main`: the owner chose no prompts at all.

## Consequences

- Work lands without the owner in the loop; the owner reviews after the fact through merged PRs.
- The review gate is now enforced only by agent behavior; the commit prompt was its last mechanical backstop.
- `test-hooks.ps1` treats any `permissionDecision` output as a regression; push cases expect exit 0 unless they force, mirror, delete or target `main`/`master`.
- A bare `git push` while on `main` is not caught by the hook (no refspec to inspect).
