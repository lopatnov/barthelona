---
paths:
  - "src/barthelona/toolchains/**"
  - "src/barthelona/executors/**"
  - "docker/**"
---
# Toolchains and executors rules (docs/architecture.md §12–§13, ADR D-006, D-010)

- Keep the protocols separate:
  - `Dialect` (assembler semantics, diagnostics parsing, header/stub rendering);
  - `Linker`;
  - `Executor` (where commands run: `tc` container, `sandbox` container, `emu` child process, later `windows-native`).

  Commands are argv tuples plus cwd, env, stdin and timeout, never shell strings.
- The worker reaches WSL through ONE long-lived WSL agent (stdlib-only `agent.py`, JSON lines), never by spawning `wsl.exe` per command.
  - The agent allow-lists `docker exec bart-tc …`, `docker run … bart-run …` (sandbox flags fixed by the agent, not the caller), `docker inspect` (exactly one target, restricted to `bart-tc` or `bart-run*`), `tar` and `sha256sum`.
  - Every path is fenced under `~/.cache/barthelona/`. Stage on ext4, never `/mnt/c`.
- Sandbox flags for generated binaries: `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 --memory 256m --memory-swap 256m --pids-limit 64 --cpus 1 --tmpfs /tmp:size=16m`, plus `timeout -s KILL`.
  - Never mount the docker socket. Never pass secrets into containers.
  - Never run generated code on Windows or in a bare WSL shell (WSL interop can launch Windows executables).
- Before assembling, pre-scan `%include`, `incbin` and fasm `file` paths and fence them to the staged project.
- Diagnostics parsers are written only against REAL captured tool output, stored in `tests/fixtures/diagnostics/<tool>/<version>/`. Capture first, then write the regex. Map paths back to project-relative paths, and compute `error_sig` with paths, numbers and symbols normalized.
- Images are pinned by digest. `barthelona probe` records the digests and `--version` of each tool in `config/toolchains.lock.json`. Never use `gcc-multilib` (it conflicts with cross compilers) or `qemu-user-binfmt`.
- Shell scripts, Dockerfiles and Makefiles are LF, ASCII where possible.
