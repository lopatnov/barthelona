# D-041: Add `docker inspect` to the WSL agent allowlist

- Status: Proposed
- Date: 2026-10-16
- Amends: D-006, D-010

## Context

`barthelona probe` (Phase 0 deliverable, `docs/architecture.md` §12) records Docker image digests
for `bart-tc` and `bart-run` in `config/toolchains.lock.json`.  The probe function
`probe_image_digest` in `src/barthelona/toolchains/probe.py` sends
`docker inspect --format {{index .RepoDigests 0}} <image>` through the `Executor` interface.

The WSL agent's allowlist (`_ALLOWED_PREFIXES` in `src/barthelona/executors/_wsl_agent.py`)
did not include `docker inspect`, so any call via a real `WslExecutor` would be rejected
at the allowlist gate while the `FakeExecutor` handled it silently in tests (issue #40).

## Decision

Add `("docker", "inspect")` to the WSL agent allowlist with the following constraints enforced
by a new `_validate_docker_inspect_argv` function:

1. **Exactly one non-flag target.** Multi-target calls (`docker inspect A B`) are rejected;
   appending an allowed image name after an arbitrary one cannot bypass the fence.
2. **Target must be `bart-tc` or a `bart-run*` image.** This limits `docker inspect` to the
   same images the agent already controls via `docker exec` and `docker run`.

## Rationale

`docker inspect` on an image does not run code; its attack surface is metadata exposure.
Restricting to exactly one target in the known set bounds the exposure to information the
agent already has (it starts and executes inside `bart-tc`, and deploys `bart-run*`).

The single-target constraint closes the multi-target bypass: an attacker who could inject
arguments cannot enumerate arbitrary images by appending `bart-tc` as a second target.

## Alternatives considered

- **Poll the registry API instead of `docker inspect`.** Requires outbound network access
  from WSL, violates the offline-first invariant, and is slower.
- **Restrict to `--format` flag only.** The `--format` flag is already required by the
  only caller, but enforcing it at the agent adds coupling to caller implementation details;
  the image-name restriction is the meaningful security boundary.
- **Leave `docker inspect` out; derive digest from `docker images --digests`.** Different
  command, same security profile; `docker inspect` is more direct and its output is stable.

## Consequences

- `probe_image_digest` now works through a real `WslExecutor` (Phase 0 prerequisite met).
- The allowlist in `docs/architecture.md` §12 and `.claude/rules/toolchains-executors.md`
  is updated to reflect the addition.
- sha256sum path fencing (`_validate_sha256sum_argv`, issue #39) and `FakeExecutor`
  limit-application (issue #41) are included in the same commit for atomicity.
