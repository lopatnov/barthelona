# D-049: The engine runs on Linux or Windows, and model endpoints may live on any PC

- Status: Proposed
- Date: 2026-10-18
- Amends: D-006, D-047

## Context

D-006 put the engine on Windows and reached the toolchains through one WSL agent. The owner (2026-10-18) says the engine does not have to run on Windows and can run on Linux, and that LM Studio and Ollama may sit on different PCs so the agent system can use more compute. The plan review (2026-10-17, finding 7, issue #103) already pointed at the cost of the Windows-only path: the agent protocol, path traps, CRLF rules, a Windows-only transport and a Linux CI transport to compensate.

What exists: D-043 already ships `AgentExecutor(transport)` with `WslTransport` and `LocalTransport` (Linux host with Docker, same agent and allow-list), and CI runs the Docker jobs on Linux. A Linux host therefore needs no new executor.

Prior art: none found in `.reference/` (not checked in this cloud session); the design follows from D-043 and D-047 as written.

## Decision

1. **Hosts.** The engine, the UI and the executors run on Linux (Debian or Ubuntu with Docker, `LocalTransport`) or on Windows 11 with WSL2 (`WslTransport`). Linux is the **reference host**: CI exercises it, and a feature is "done" when it passes there. Windows stays supported for the owner's Windows PC and is covered by the `wsl` tests. Nothing in `engine`, `nodes`, `verification` or `llm` may assume a host OS; host differences stay inside `executors` transports, `scripts/` and `docs/runbook.md`.
2. **Model endpoints across PCs.** Any PC that serves an OpenAI-compatible API (LM Studio or Ollama, on Windows, Debian or macOS) is an endpoint in the catalog (D-047). The gateway needs only HTTP reach. Loopback endpoints keep the `127.0.0.1` rule; LAN endpoints (`network: lan`) are allowed for providers marked `local: false` and must be listed explicitly (F-7).
3. **What "more compute" means.** The scheduler (D-047) runs independent calls in parallel on different endpoints (sprint layers already fan out per task, §7), sends roles to the endpoint that holds the right model (planner on the strongest PC, coders on the fast ones), and fails over when an endpoint dies (§16.6). It does **not** shard one model across PCs. That needs a different runtime (llama.cpp RPC, vLLM, exo) and is parked.
4. **Endpoint pool is pulled forward.** The `endpoints[]` loader lands with the Phase 1a gateway, and least-loaded scheduling with affinity in Phase 1b, instead of "Phase 2 or later" (issue #44). A single PC still works with one endpoint.
5. **Toolchains stay local to the engine host** (D-047 item 5): remote toolchain hosts remain out of scope. Models are remote-capable; execution is not.

## Rationale

Linux as the reference host removes the layer that cost the most Phase 0 effort (D-041, D-043, path traps, stderr loss, mount TOCTOU) from the critical path and tests the real thing in CI, while Windows users keep the existing path. Models are the scarce resource for quality and speed, and they are already behind HTTP, so spreading them over PCs is cheap and does not touch the sandbox invariants.

## Alternatives considered

- **Windows-only engine (D-006 as written).** Keeps ml64 and LM Studio on the host loopback, but forces every feature through the WSL bridge. ml64 is a Phase 4 opt-in and can run as its own executor (`windows-native`).
- **Linux-only.** Simplest, but drops the owner's primary PC.
- **Remote toolchain hosts.** More throughput for builds, but a new trust boundary for generated code; not needed while models are the bottleneck.

## Consequences

- `docs/architecture.md` §1 (machine), §3 (placement) and §12 (bridge) are updated in the same change.
- Phase 1a gets a CI job that runs the walking skeleton on Linux with `FakeGateway`. The `wsl` marker tests stay.
- `config/models.yaml` loader work (F-13, #25, F-7) moves into Phase 1a.
- Issue #103 (WSL spike) is closed by this decision; no separate spike.
- `AGENTS.md` still describes the Windows host; wording follows in a gated change (F-71).
