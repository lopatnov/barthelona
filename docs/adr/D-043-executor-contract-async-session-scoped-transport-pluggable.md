# D-043: Executor contract: async, session-scoped, transport-pluggable

- Status: Proposed
- Date: 2026-10-17
- Amends: D-006, D-010

## Context

The architecture review (issue #63) found that the `Executor` protocol does not fit the engine that will call it:

- The engine is asyncio and runs one `Send` per task in parallel (`docs/architecture.md` §7), but `Executor.run`, `stage` and `collect` are synchronous.
- `WslExecutor` keeps the per-attempt work directory in a mutable attribute (`_work_dir`) that the worker is expected to reassign before each run. `stage()` and `collect()` take no run or attempt argument, so two tasks in flight overwrite each other.
- The agent link is one pipe: one JSON line out, one line back, no request id, and the agent handles one request at a time. A slow command blocks every other task.
- The verification ladder and the probe build `docker exec bart-tc ...` themselves, so the oracle layer knows the container transport and the "tc" executor does not own its container.
- `WslExecutor` refuses to start off Windows. GitHub Actions and cloud threads cannot run the real assemblers, so a green CI says nothing about the oracles.

## Decision

1. **Async and session-scoped.** The protocol becomes `open_session(run_id, attempt) -> Session`, where a `Session` owns one work directory and offers `async stage(tar)`, `async run(cmd, limits)`, `async collect()` and `close()`. The executor has no mutable work directory. Blocking transport I/O runs in a worker thread inside the executor, so callers never block the event loop.
2. **Multiplexed agent protocol.** Every request carries an `id` and every reply echoes it. The agent runs requests concurrently in a bounded pool (default 4). The first message is a `hello` with a protocol version; a mismatch is an `infra_error`. The agent file hash check stays.
3. **The executor owns its environment.** Callers pass the tool argv (`nasm -f elf64 ...`) to the `tc` executor, which wraps it in `docker exec bart-tc`. The `sandbox` executor wraps `docker run` with the fixed flags. Callers never see `docker`.
4. **Pluggable transport.** `AgentExecutor(transport)` with `WslTransport` (the `wsl.exe` pipe, Windows) and `LocalTransport` (spawns the same stdlib agent directly with `python3`, on a Linux host with Docker). The allow-list, path fence and sandbox flags live in the agent and apply to both; the allow-list never admits a generated binary or an arbitrary path on the host. The `docker` marker is registered in `pyproject.toml` and `.claude/rules/python.md` when it is introduced.
5. **Tests.** Toolchain tests that need only Docker get a `docker` marker and run in CI once `bart-tc` builds there. The `wsl` marker keeps the tests that need the Windows bridge itself.

## Rationale

The agent already is the security boundary (allow-list, path fence, fixed sandbox flags). Moving the transport behind a protocol keeps that boundary single and lets the same code run on the owner's PC and in Actions, which the Phase 0 backlog needs (Docker images are built and tested there). Request ids are the smallest change that makes one long-lived agent usable by parallel tasks, and they keep the measured 150 ms warm-call advantage.

## Alternatives considered

- **Keep the sync API and wrap calls in `to_thread` at each call site.** Every caller repeats it, the shared work directory problem remains.
- **One agent process per task.** Costs a `wsl.exe` start per task and contradicts the "one long-lived agent" decision of D-006.
- **Docker SDK or `docker` CLI directly from the engine.** Drops the agent's fence and does not work from Windows without exposing the Docker socket.
- **Asyncio subprocess pipes on Windows only.** Still needs request ids on the wire; does not fix the Linux CI gap.

## Consequences

- Changes `executors/`, `verification/ladder.py`, `toolchains/probe.py`, `FakeExecutor` and their tests (issue #63). Do it before the `bart-run` executor and V5/V6 (#47).
- `docs/architecture.md` §3 and §12 are updated in the same change.
- Invariant 2 is unchanged: generated binaries still run only through the `sandbox` executor or the emulator child. `LocalTransport` only drives the same allow-listed Docker commands.
