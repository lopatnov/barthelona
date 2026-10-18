# D-048: CI/CD workflows are a deterministic scaffold output, selected by target family

- Status: Proposed
- Date: 2026-10-18
- Amends: D-008, D-045

## Context

The plan covered how a project is built and verified inside barthelona, but not how the produced project is built and verified on its own after the owner publishes it. The owner noticed this on 2026-10-18 while the Snake demo got hand-written workflows (`barthelona-simplest-demo/.github/workflows/`). For assembler the setups are few and typical: assemble and link with a known toolchain, run the project's tests, and publish the binary on a version tag. They can be prepared in advance, like `gen/` and the Makefile.

Prior art:
- `lopatnov/barthelona-simplest-demo` `ci.yml` (verify ladder in the sandbox) and `release.yml` (tag build and publish): the starting point for both templates.
- `docs/architecture.md` §6.1 step 7 and §18: the scaffold step already emits `gen/`, the Makefile and `.gitattributes`; CI files fit the same step.
- GitHub Actions hardening guidance (SHA-pinned actions, least-privilege `permissions`) already applied in this repo's own `.github/workflows/ci.yml`.

## Decision

1. The scaffold step (`header_gen`, deterministic, never an LLM) also writes `.github/workflows/ci.yml`, `.github/workflows/release.yml` and `.github/dependabot.yml` into the workspace.
2. Templates live in `src/barthelona/scaffold/templates/<family>/` and are rendered by `barthelona.scaffold.render_ci(project, barthelona_ref)`. A **family** is a target the project is built for. Only `linux-x64` exists (NASM, GAS Intel, GAS AT&T; ELF64; `ld`). Any other target fails with `UnsupportedCiTarget` (`StopReason.UNSUPPORTED_TARGET`) instead of getting a workflow that cannot work.
3. `ci.yml` installs barthelona at a pinned commit from its hash-locked runtime lock, builds the `bart-tc`/`bart-run` images, runs `barthelona verify --level V6 --json` and fails unless every required level (default `tamper V0 V1 V2 V5 V6`) reports `pass` and no level reports `fail`. The generated project is therefore judged by the same oracles as inside barthelona (invariant 1); the workflow adds no weaker check.
4. `release.yml` runs on a `v*` tag (the per-increment tags of §18 are release candidates), refuses to publish unless `ci.yml` succeeded for that commit, assembles and links with the plain toolchain, checks that the output is an x86-64 ELF without running it (invariant 2), writes a SHA-256 file and publishes both with generated release notes.
5. Every action is pinned to a commit SHA, each workflow declares least-privilege `permissions`, and Dependabot keeps the pins current.
6. Templates are tested in barthelona's own CI: a unit test renders each dialect, parses the YAML, rejects leftover placeholders and unpinned actions; `yamllint --strict` covers the template files; a CI job renders a sample project and runs actionlint on it.
7. Workflows are generated once, then belong to the owner of the project. Regeneration overwrites them only when the owner asks, and edit mode never touches `.github/`.
8. Later families arrive with their presets (Phase 4): Windows x64 (mingw, wine runner or a `windows-latest` job at V8), ELF32, boot sector (qemu); AArch64 and RISC-V (qemu-user, Phase 5). Each preset's conformance kit includes a rendered CI template.

## Rationale

Typical assembler projects need no creativity in CI, only correctness, so a template is cheaper and safer than asking a model. Running the real ladder in CI means the owner's repo keeps the guarantees after leaving barthelona. Pinning the verifier commit keeps old projects reproducible.

## Alternatives considered

- **Let the coding agent write workflows.** Non-deterministic, unreviewable per run, and a workflow can exfiltrate secrets; templates are tested once.
- **Only a Makefile and a README line.** Misses verification on pull requests and tagged releases.
- **A reusable workflow in the barthelona repo that projects call.** Lower duplication, but couples every project to one repository's availability and ref; revisit once the template set stabilises.

## Consequences

- Scaffold wiring waits for the engine (Phase 1a); the library, templates and tests land now (issue #126).
- The `verify` exit-code problem (F-67, #123) is worked around by reading the JSON report; when `--require` lands, the step becomes one line.
- The same step is the natural home for the other standard repo files tracked in issue #127 (LICENSE, `.gitignore`, build and run README sections, release notes, SECURITY).
- Release provenance (artifact attestations) and signing are not in v1.
- `scaffold` imports only `domain` and is added to D-045's dependency matrix (amends D-045).
- Project-derived values never reach a workflow if they contain a GitHub expression (`${{`), because Actions expands it before the shell and quoting cannot stop it.
- Generated CI checks out `lopatnov/barthelona` at the pinned commit, so that repository must stay reachable and the commit must never be rewritten.
- The actionlint image in barthelona's own CI is pinned by tag (`1.7.7`), not digest; digests of third-party images are not resolvable from this environment, so the pin is a follow-up for the first PC session.
- Nothing runs the generated `ci.yml` end to end yet; the Snake demo is the first real run (its workflow is the template's ancestor).
