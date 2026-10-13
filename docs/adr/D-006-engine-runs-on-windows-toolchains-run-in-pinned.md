# D-006: Engine runs on Windows; toolchains run in pinned WSL Docker images through one persistent WSL agent

- Status: Proposed
- Date: 2026-10-13

## Decision

Placement:
- Python (UI, engine, Unicorn/Capstone) runs on Windows in the conda env.
- Assemblers, linkers and binutils run in the long-lived bart-tc container (docker exec).
- Generated binaries run in ephemeral bart-run containers.

The bridge to WSL:
- One long-lived `wsl.exe -d Ubuntu -e python3 agent.py` process.
- It speaks JSON lines and stages each run as a tar to ~/.cache/barthelona/runs on ext4.
- It allows only allow-listed argv commands.

The image digest plus each tool's --version form the toolchain lock.

## Rationale

Why the engine stays on Windows: conda, LM Studio on the host loopback (127.0.0.1), and a future native ml64 all live there.

Why containers: WSL lacks nasm, fasm, gdb and qemu today, and pinned images are reproducible without apt drift.

Why one persistent agent:
- A warm wsl.exe call costs about 150 ms and docker run 0.5–0.9 s (measured).
- /mnt/c is slow 9P and is wrong for builds.

## Alternatives considered

- Engine inside WSL: LM Studio needs host networking, and conda is on Windows. Revisit only if path or latency friction grows.
- apt-installed tools run directly in WSL (pragmatist): less reproducible, and not isolated from WSLInterop. Allowed only as an optional developer convenience.
