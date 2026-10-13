---
name: asm-check
description: Manually assemble, link and (optionally) run a small hand-written assembly file or fixture during development, safely - assembling in WSL and running the binary only inside a locked-down docker container. Use while writing fixtures, rule cards, mutation-corpus entries or dialect adapters, until the product's own `barthelona verify` exists.
argument-hint: "<path-to-asm> [nasm|gas] [static|libc] [run]"
---
# Manual assembly check (dev-time)

Arguments: `$ARGUMENTS`. The first token is the path. Classify the remaining tokens by value, in any order:
- `nasm` / `gas`: the dialect (default: from the file's header comment, else `nasm`);
- `static` / `libc`: the link mode (default `static`);
- `run`: run the binary in the sandbox (otherwise build and inspect only).

Once Phase 0 lands, prefer `python -m barthelona verify` (see `docs/roadmap.md`). This skill is the manual fallback.

## Safety rules (D-010)

- Never execute a built binary on Windows or directly in a WSL shell. Run it only in the docker sandbox below.
- Assembling and linking with the real tools is fine.
- Stage files on WSL ext4 (`~/.cache/barthelona/devcheck/`), never build on `/mnt/c`.
- Don't install packages. If `nasm` (or another tool) is missing in WSL, tell the user the exact command (`sudo apt-get install -y nasm`) and stop. Installing is the owner's action.

## Steps

1. **Preflight.**
   - `wsl.exe -l --running -q` shows whether the VM is up. If it is not, starting it with `wsl.exe -d Ubuntu -e true` is fine.
   - Then `wsl.exe -d Ubuntu -e bash -lc "command -v nasm as ld gcc docker"`.
2. **Stage.** Convert the Windows path with `wslpath`, copy the file into a fresh `~/.cache/barthelona/devcheck/<name>/`, and ensure LF line endings: `sed -i 's/\r$//'`.
3. **Assemble and link** inside WSL (one `bash -lc` call):
   - NASM static: `nasm -f elf64 -g -F dwarf -Xgnu -w+all prog.asm -o prog.o && ld -o prog prog.o`
   - NASM libc: `nasm -f elf64 -g -F dwarf -Xgnu prog.asm -o prog.o && gcc -no-pie -o prog prog.o` (or PIE with `default rel` and `wrt ..plt`)
   - GAS static: `as --64 -g --fatal-warnings prog.s -o prog.o && ld -o prog prog.o`
   - GAS libc: `gcc -o prog prog.s`

   Report diagnostics verbatim, with `file:line`, then explain them, using the `asm-docs` skill for the relevant manual section.
4. **Inspect**, with no execution: `objdump -d -Mintel prog | head -80`, `nm prog`, `readelf -h -l prog`.
5. **Run** (only if `run` was given), in a throwaway container with no network, no capabilities, a read-only root and limits:
   ```
   docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
     --user 65534:65534 --memory 256m --memory-swap 256m --pids-limit 64 --cpus 1 \
     --tmpfs /tmp:size=16m -v "$HOME/.cache/barthelona/devcheck/<name>:/work:ro" \
     <image> timeout -s KILL 10 /work/prog; echo "exit=$?"
   ```
   - `<image>`: `busybox` for static binaries, `python:3.12-slim` (glibc) for libc-linked ones. Both are already present in WSL docker. Never pull other images without asking.
   - Report stdout, stderr and the exit code.
6. **Clean up** the staging directory unless the user wants to keep it.

Each `docker` call triggers a permission prompt. Show the full command so the owner can approve it.
