---
name: env-doctor
description: Check the barthelona development environment (conda env and imports, lock freshness, cloud API keys present - names only, LM Studio and loaded model, Ollama, WSL and its tools, docker containers/images, Qdrant, .wslconfig, Claude Code version) and explain how to fix what is missing. Use at the start of work, when something environment-related fails, or when the user asks "is everything set up?".
argument-hint: "[--start-wsl]"
---
# Environment doctor

Run the read-only health check with the PowerShell tool, from the repo root:

- Default: `.\scripts\doctor.ps1`. It does not boot the WSL VM.
- With `-StartWsl`, it also checks WSL tools, docker and Qdrant. Use this when the user passed `--start-wsl`, or when the task needs WSL.

Then:
1. Summarize the result: what is OK, and what needs attention, in order of impact on the current task.
2. For each problem, give the exact fix and say whose action it is:
   - **Claude can do:** start the LM Studio server (`lms server start`), or build the env (`.\scripts\create_env.ps1`). Both ask for permission.
   - **Owner only:** API keys in `.env`, `.wslconfig`, `sudo apt-get install ...` in WSL, the Qdrant storage migration, `claude update`. Point to the matching section of `docs/runbook.md`.
3. Never print or read API key values or `.env`. The script reports key names only.
4. Do not change any configuration as part of this skill.

Known expected states:
- The WSL VM is often stopped, so Qdrant (:6333) and the Qdrant MCP (:8000) are unreachable until it boots. After a boot, Qdrant needs tens of seconds to load from `/mnt/c`.
- nasm, fasm, gdb and qemu are not installed in WSL by design: the product uses pinned Docker images (Phase 0).
- `barthelona/toolchain` and `barthelona/runner` images do not exist until Phase 0.
