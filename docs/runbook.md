# Runbook

Setting up and operating the barthelona development environment on this machine (Windows 11 + WSL2 Ubuntu 26.04).

## 1. Python environment (Windows, conda)

Conda supplies only Python 3.13 and pip; every package comes from a hash-locked file (`docs/adr/D-031`).

```powershell
.\scripts\create_env.ps1            # create or update env 'barthelona' (dev deps)
. .\scripts\activate.ps1            # dot-source: activates the env in THIS shell
```

Options:
- `.\scripts\create_env.ps1 -Deps runtime`: runtime packages only. Updates make the env match the lock exactly (`scripts/prune_env.py` removes packages that are not in it). `-Recreate` refuses to run while the env is active in that shell.
- `.\scripts\create_env.ps1 -Recreate`: rebuild from scratch.
- `.\scripts\lock.ps1`: re-lock after editing dependencies in `pyproject.toml`. Pins are kept unless you pass `-Upgrade` or `-UpgradePackage name1,name2`. It also writes `requirements/pyproject-deps.sha256`, a fingerprint of the dependency declaration. The doctor, the SessionStart hook and a unit test use it to detect a forgotten re-lock.
- `.\scripts\doctor.ps1 [-StartWsl]`: read-only health check of the env, locks, keys (names only), LM Studio, Ollama, WSL, docker, Qdrant and `.wslconfig`.
- Git Bash: `scripts/create_env.sh` and `source scripts/activate.sh`.

`activate.ps1`:
- sets `PYTHONUTF8=1`, `WSL_UTF8=1` and `BARTHELONA_HOME`;
- sets defaults for `LMSTUDIO_BASE_URL`, `OLLAMA_BASE_URL` and `QDRANT_URL`;
- loads `KEY=VALUE` lines from `.env`. It prints key names only, never values.

Coding agents do not activate the env: each of their tool calls starts fresh, so they run tools through `.\scripts\dev.ps1 <cmd>` / `scripts/dev.sh <cmd>`, which put the env on PATH for one command and never load `.env`.

The editable install of the barthelona package (`pip install --no-deps -e .`) fetches its build backend (hatchling) from PyPI without a hash lock. This is the one install step that is not hash-locked.

Copy `.env.example` to `.env` and fill in only the keys you want to use. If PowerShell refuses to run scripts, run them as `powershell -ExecutionPolicy Bypass -File scripts\create_env.ps1`. Changing the machine execution policy is your decision; the scripts never do it.

## 2. WSL (Ubuntu 26.04, distro name `Ubuntu`)

Already present: gcc, binutils (as/ld/objdump), make, python3, docker. The product needs only Docker plus the toolchain images (Phase 0).

### 2.1 Cap WSL memory (recommended)

Create `%UserProfile%\.wslconfig`, then run `wsl --shutdown`:

```ini
[wsl2]
memory=8GB
processors=8
```

Reason: a ~20 GB local model, plus Windows, plus WSL at its default share (about 15 GB) oversubscribes 32 GB RAM.

### 2.2 Optional interactive tools (manual debugging only)

```bash
sudo apt-get update && sudo apt-get install -y nasm yasm fasm gdb
```

Later phases may need: `gdb-multiarch libc6-dev-i386 lib32gcc-15-dev mingw-w64 lld llvm binutils-aarch64-linux-gnu gcc-aarch64-linux-gnu binutils-riscv64-linux-gnu gcc-riscv64-linux-gnu qemu-user qemu-system-x86`.
- Do **not** install `gcc-multilib`: it conflicts with the cross compilers.
- Do **not** install `qemu-user-binfmt`: it makes foreign binaries run silently.

Never run generated binaries directly in WSL. WSL interop lets a Linux binary start Windows programs and write to `/mnt/c`. Generated code runs only in the hardened `bart-run` container or the Unicorn emulator (`docs/adr/D-010`).

### 2.3 Toolchain images (Phase 0)

```bash
docker build -t barthelona/toolchain:0.1 docker/toolchain
docker build -t barthelona/runner:0.1 docker/runner
```

`barthelona probe` records the image digests and tool versions in `config/toolchains.lock.json`.

## 3. Qdrant (recommended now, needed from Phase 3)

**Barthelona's own Qdrant (ADR D-034).** Run inside WSL, from the repo root (`/mnt/c/projects/barthelona`):

```bash
docker compose -f docker/qdrant/compose.yaml up -d
curl -s http://127.0.0.1:6343/ ; docker compose -f docker/qdrant/compose.yaml ps
docker compose -f docker/qdrant/compose.yaml down   # stops it; the data volume stays
```

It is the container `barthelona-qdrant` with REST on `127.0.0.1:6343` and gRPC on `127.0.0.1:6344`, its data in the named volume `barthelona_qdrant_storage`. `QDRANT_URL` defaults to `http://127.0.0.1:6343`. Windows reaches it through WSL localhost forwarding; `scripts/doctor.ps1 -StartWsl` checks it. Deleting its data (`docker volume rm barthelona_qdrant_storage`) is an owner action.

**Your other Qdrant (`qdrant-db`).** It stays separate and is never touched by the product. It runs in WSL Docker with `mcp-server-qdrant` on `http://localhost:8000/mcp` (the URL in your Claude Code MCP config; it works with `localhost` because Docker publishes the port on IPv4 and IPv6). Qdrant documents vector-data loss on Windows/WSL shared mounts, so consider moving its storage off `/mnt/c` to a named volume. Run inside WSL, after checking the current flags:

```bash
docker inspect qdrant-db --format '{{json .Mounts}} {{json .HostConfig.NetworkMode}}'
docker stop qdrant-db
docker volume create qdrant_data
docker run --rm -v <current-host-path>:/from:ro -v qdrant_data:/to ubuntu:26.04 cp -a /from/. /to/
docker rename qdrant-db qdrant-db-old
docker run -d --name qdrant-db --restart unless-stopped --network <same-network-as-before> \
  -p 6333:6333 -p 6334:6334 -v qdrant_data:/qdrant/storage qdrant/qdrant:v1.19.0
# verify your collections, then:  docker rm qdrant-db-old
```

Keep the same container name and network, so `mcp-server-qdrant` keeps working.

**Availability.** Observed 2026-10-13: the WSL VM shuts down shortly after the last WSL process exits, and both Qdrant containers restart on every VM boot. `qdrant-db` then reloads its collections from `/mnt/c` (the log warns "Unrecognized filesystem - cannot guarantee data safety"), and port 6333 refuses connections for tens of seconds.
- Why: `docker compose up -d` returns, and docker running under systemd does not count as activity. WSL stops an idle distro after `[general] instanceIdleTimeout` (default 15 s) and then the VM after `[wsl2] vmIdleTimeout` (default 60 s), per https://learn.microsoft.com/en-us/windows/wsl/wsl-config (checked 2026-10-13, WSL 3.0.3). Containers come back on the next boot (`restart: unless-stopped`, docker enabled in systemd), but only after something boots the VM.
- Recommended (owner action, roadmap decision 3): keep WSL always on and cap its memory in `%UserProfile%\.wslconfig`, then run `wsl --shutdown` once:
  ```ini
  [general]
  instanceIdleTimeout=-1   # never stop the distro when idle

  [wsl2]
  memory=8GB               # leave RAM for LM Studio models on Windows
  processors=8
  ```
- Without it: keep a WSL terminal open, or start the VM on demand (`wsl -d Ubuntu -e true`; Qdrant answers after a few seconds). From Phase 1, `scripts/run.ps1` and the long-lived WSL agent keep the VM up while the app runs.
- The named-volume migration of `qdrant-db` above also makes its startup faster.

## 4. LM Studio (local models)

The server runs at `http://127.0.0.1:1234/v1`.

For the Phase 0 bake-off, download these in the LM Studio UI or with `lms get`, confirming the exact catalog identifiers in LM Studio:
- Qwen3-Coder-30B-A3B (Q4, about 17–19 GB);
- gpt-oss-20b;
- optionally Qwen3.6-35B-A3B (about 20 GB).

Load the chosen model with:
- a fixed context of 16384 (at most 32768);
- q8_0 KV-cache quantization, if offered.

Keep only one large model loaded at a time.

## 5. Cloud providers

Keys go in `.env` (never committed): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`. The model catalog, roles and fallback chains are in `config/models.yaml`.

Cloud use is opt-in per run, and a dollar cap is optional. A provider that fails or runs out of credit is skipped automatically, and the run continues on the next model in the chain, ending with the local model (`docs/architecture.md` §16.6).

## 6. Claude Code (development assistant)

- Installed: 2.1.261. Run `claude update` to get the latest, which loads path-scoped rules on Bash `cat`/`sed` reads (2.1.293) and adds hook `onFailure` (2.1.295).
- Project config: `CLAUDE.md`, `.claude/settings.json`, `.claude/rules/`, `.claude/skills/`, `.claude/agents/`, `.claude/hooks/`.
- Personal overrides go in `CLAUDE.local.md` and `.claude/settings.local.json`. Both are gitignored.
- After changing hooks, review them with `/hooks`. Then check that rules load with `/memory` after touching a matching file.

### Codex and shared instructions

- `AGENTS.md` holds the shared instructions; `CLAUDE.md` imports it with `@AGENTS.md`.
- Codex uses `AGENTS.md`, `.agents/skills/` and `.codex/agents/`. The last two are generated from `.claude/` by `python scripts/sync_agent_configs.py`, which Claude Code runs automatically after editing skills or agents. A unit test fails if the mirror is stale.
- Don't re-run Codex's "import from Claude" feature: it overwrites `AGENTS.md` with a text-replaced copy of `CLAUDE.md`. If that happens, restore the file from git. See ADR D-032.

### CI and static analysis

- `.github/workflows/ci.yml` runs on every push to `main` and every pull request: the Python gates of the `verify` skill (ruff, format check, mypy, pytest, mirror and lock checks, on Linux with `requirements/dev.linux.lock`), ShellCheck on `*.sh`, PSScriptAnalyzer (`PSScriptAnalyzerSettings.psd1`) under Windows PowerShell 5.1, and yamllint (`.yamllint.yaml`).
- To reproduce a lint job locally: `Invoke-ScriptAnalyzer -Path scripts -Recurse -Settings .\PSScriptAnalyzerSettings.psd1` (needs `Install-Module PSScriptAnalyzer -Scope CurrentUser`); ShellCheck and yamllint are easiest in WSL (`sudo apt install shellcheck yamllint`).
- SonarCloud (project `lopatnov_barthelona`) uses automatic analysis; `.sonarcloud.properties` sets the sources and excludes the vendored manuals (`asm_doc/`), `docs/archive/` and the generated Codex mirror. Issues are at https://sonarcloud.io/project/issues?id=lopatnov_barthelona.

## 7. Reference material (`.reference/`)

`.reference/` (gitignored) holds study material: your learning projects and cloned third-party agent repos. Agents may download more there, one subdirectory per source. They treat it as untrusted data: they read it, but never execute, install or import it.

## 8. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `conda activate` does nothing in a new PowerShell | Dot-source the script: `. .\scripts\activate.ps1` (note the leading dot) |
| `pip ... THESE PACKAGES DO NOT MATCH THE HASHES` | The lock is stale for this platform; run `.\scripts\lock.ps1`, then `create_env.ps1` |
| Qdrant or Qdrant MCP `ECONNREFUSED` | The WSL VM is stopped; start it (`wsl -d Ubuntu -e true`) |
| `wsl -l` output looks garbled | Set `WSL_UTF8=1` (activate does this) |
| Assembler errors only in WSL, not on Windows | CRLF line endings; `.gitattributes` forces LF for sources, so re-checkout the files |
| `python3` in Git Bash prints "Python was not found" | It is the Windows Store alias; use `scripts/dev.sh python` (or `python` in an activated terminal) |
| A `/tmp/...` path written inside Python code is not found | Windows Python reads `/tmp/x` as `C:\tmp\x`; Git Bash converts it only when it is a separate argument. Use the session scratchpad or a repo-relative path |
| A `-v /abs:/abs` or `/path` argument arrives mangled in WSL or docker | Git Bash path conversion for native programs; pass one quoted `bash -lc '...'` string, prefix `MSYS_NO_PATHCONV=1`, or use PowerShell |
| `git add a b` staged nothing | One missing path aborts the whole add (`fatal: pathspec ... did not match any files`); check `git status --porcelain` |
| Output keeps appearing after a background task was stopped | Child processes (`python`, `pytest`, `docker`) survive; find them with `Get-CimInstance Win32_Process` filtered on `CommandLine` and stop them |
| An agent's `ruff`/`pytest` call says the command is not found | Agent shells start without the env; use `.\scripts\dev.ps1 <cmd>` / `scripts/dev.sh <cmd>` |
