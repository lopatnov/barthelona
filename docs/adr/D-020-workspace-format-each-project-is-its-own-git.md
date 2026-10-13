# D-020: Workspace format: each project is its own git repository

- Status: Proposed
- Date: 2026-10-13

## Decision

Contents of <workspaces>/<slug>/:
- project.yaml, contracts.yaml, src/
- gen/ (generated, committed)
- tests/ (locked)
- Makefile, .gitattributes (eol=lf)
- .barthelona/ (backlog, sprints, repomap, overlay)
- build/ (ignored)

The default root is <repo>/workspaces/ (gitignored), configurable with BARTHELONA_WORKSPACES.

Git model: a branch per run, a commit per green task, a tag per increment.

## Rationale

A project that builds without barthelona is a usable deliverable.

Git gives rollback and diffs for G4.

The LF rule avoids breaking WSL builds.

## Alternatives considered

- Store projects inside var/: not user-friendly.
- A single shared repo: tangles runs.
