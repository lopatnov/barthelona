# D-010: Sandbox execution policy

- Status: Proposed
- Date: 2026-10-13

## Decision

bart-tc:
- --network none, non-root, read-only root filesystem;
- include/incbin/file paths fenced to the project;
- NASM --limit-* options, fasm pass limits, timeouts.

Generated binaries run in fresh bart-run containers with:
- --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534
- memory, pids, cpu, ulimit and tmpfs limits
- the workdir mounted read-only
- timeout -s KILL

The Unicorn child has syscall and interrupt allow-lists plus instruction and time caps.

Never: the Windows host, a bare WSL shell (WSLInterop is enabled), a mounted Docker socket, shell=True, or an LLM shell.

## Rationale

Generated code and imported repos are untrusted. Assembler macro languages can loop forever or read host files.

WSLInterop is enabled (measured), so WSL alone is not a boundary.

## Alternatives considered

- Run in WSL directly: unsafe.
- Windows Sandbox for everything: 30–60 s per run, and no stdout from `wsb exec`. Kept as opt-in level V8.
