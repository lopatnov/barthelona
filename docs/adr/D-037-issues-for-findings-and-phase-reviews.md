# D-037: Every finding becomes a GitHub issue; each phase ends with a full review

- Status: Proposed
- Date: 2026-10-14
- Amends: D-033

## Context

Until now, problems that agents found (their own, a reviewer's, a review bot's, "Found while here") were fixed in place or written down only as rows in `docs/roadmap.md` Follow-ups. On GitHub nothing showed what was open, and a PR did not say which extra problems it fixed. Phases also had exit criteria but no review of the whole: whether the code really runs end to end, whether its style holds up, and whether a newcomer can install, configure, run and debug it from the docs alone. On 2026-10-14 the owner asked for both.

## Decision

- **Findings become issues.** When an agent finds a problem or bug, it opens a GitHub issue right away. This covers its own problems, a reviewer's or bot's finding, and anything it notices outside the task. When the fix is in scope, it lands in the task's PR: the description carries `Fixes #N` and a line saying which extra issues the PR also fixes. A deferred item keeps its open issue, and its `docs/roadmap.md` Follow-ups row cites that issue.
- **Phase review.** When a roadmap phase meets its exit criteria, a full review runs before the next phase starts. It covers:
  - the code works: run it and smoke-test it end to end;
  - style and best practices (`.claude/rules/python.md`);
  - project docs: what barthelona is and how to use it;
  - process docs: installing, configuring, running and debugging from the docs alone.

  Every finding becomes an issue. The phase counts as done once the review has run and its blocking issues are fixed.

## Rationale

Issues make open problems visible and countable, and they link each fix to the PR that made it. A phase review catches what per-PR reviews miss: whether the pieces work together, and whether the documentation is enough on its own.

## Alternatives considered

- Keep roadmap rows only: there is no link from the fixing PR, and the rows are invisible on GitHub.
- Review only per PR: never checks the whole, the end-to-end behavior or the docs.

## Consequences

- More issues, including small ones. Each needs only a few lines.
- Roadmap Follow-ups rows and issues overlap for deferred items. The row keeps the planning context and the issue tracks the state.
- Each phase grows by one review step, which goes into the roadmap's exit criteria.
