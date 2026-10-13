# D-034: Barthelona runs its own Qdrant from docker/qdrant/compose.yaml

- Status: Proposed
- Date: 2026-10-13
- Amends: none

## Context
The owner's existing Qdrant (`qdrant-db`, WSL Docker, port 6333) is shared with other projects and Claude Code's Qdrant MCP, and keeps its storage on a `/mnt/c` bind mount, which Qdrant documents as unsafe (https://qdrant.tech/documentation/common-errors/, checked 2026-10-13).

## Decision
The product uses a project-owned Qdrant defined in `docker/qdrant/compose.yaml`:
- compose project `barthelona`, container `barthelona-qdrant`, image pinned to `qdrant/qdrant:v1.19.0`;
- storage in the named volume `barthelona_qdrant_storage` (WSL ext4), never a Windows mount;
- REST on `127.0.0.1:6343`, gRPC on `127.0.0.1:6344` (loopback only, no clash with `qdrant-db`);
- telemetry off; `QDRANT_URL` defaults to `http://127.0.0.1:6343`.

`qdrant-db` and its MCP server stay the owner's development aid and are never touched by the product or agents.

## Rationale
Isolation (collections, versions and restarts are independent of other projects), safe storage, a reproducible setup in the repo, and no port conflict.

## Alternatives considered
- Reuse `qdrant-db`: shared state, unsafe storage, version drift with other projects.
- Qdrant local mode (embedded in Python): no server, but RRF support in local mode is unverified (architecture §18) and it cannot be shared by the UI and workers.
- Bind-mount storage under the repo: the repo is on `/mnt/c`, the unsafe case.

## Consequences
- Reachable only while the WSL VM runs, like every WSL service (runbook §3).
- Compose files are gated paths (`docker/**`): changes need the review gate.
- Removing the data needs `docker volume rm barthelona_qdrant_storage`, an owner action (the guard blocks volume removal for agents).

