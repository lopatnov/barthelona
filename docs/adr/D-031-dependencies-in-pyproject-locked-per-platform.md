# D-031: Dependencies are declared in pyproject.toml and hash-locked per platform

- Status: Proposed
- Date: 2026-10-13
- Amends: D-023

## Decision

- `pyproject.toml` is the single place where Python dependencies are declared: `[project.dependencies]` plus the extras `dev`, `kb`, `obs` and `ingest-pdf`. D-023 did not say where dependencies are declared; this ADR makes `pyproject.toml` the only place.
- `scripts/lock.ps1` compiles four hash-locked files with `uv pip compile --generate-hashes` for Python 3.13:
  - `requirements/runtime.win.lock` and `requirements/dev.win.lock` (`x86_64-pc-windows-msvc`);
  - `requirements/runtime.linux.lock` and `requirements/dev.linux.lock` (`x86_64-unknown-linux-gnu`, for a future engine-in-WSL or CI).
- `scripts/create_env.ps1` (and its Bash twin `create_env.sh`) creates the conda env from `environment.yml` (python 3.13 + pip only), installs the lock with `--require-hashes --no-deps`, then runs `pip install --no-deps -e .` and `pip check`.
- `scripts/activate.ps1` / `activate.sh` must be dot-sourced or sourced. They load the conda hook if needed, activate the env, set `PYTHONUTF8`, `WSL_UTF8`, `BARTHELONA_HOME` and the local endpoint defaults, and load `.env` without executing it or printing values.
- Existing pins are kept on re-lock unless `-Upgrade` or `-UpgradePackage` is passed.
- Installs are exact: after installing a lock, `scripts/prune_env.py` uninstalls packages that are not in it. The editable install's build backend (hatchling) is the one unhashed download.
- Agents run tools through `scripts/dev.ps1` / `dev.sh` (env on PATH for one command, no `.env`); `activate.*` is for the owner's own terminal.
- `lock.ps1` also writes `requirements/pyproject-deps.sha256`: a sha256 of `requires-python`, `dependencies` and `optional-dependencies` (`scripts/deps_fingerprint.py`). `doctor.ps1`, the SessionStart hook and `tests/unit/test_package.py` compare it. A dependency edit without a re-lock is caught, while unrelated `pyproject.toml` edits (tool config) are not flagged.

## Rationale

- One declaration avoids drift between `pyproject.toml` and `*.in` files.
- Per-platform locks avoid hash mismatches between Windows and Linux wheels.
- On 2026-10-13 the dev closure resolved to 130 pinned packages on Windows and 128 on Linux, including langgraph 1.2.15, streamlit 1.65.0, anthropic 1.13.0, openai 3.29.0, google-genai 2.30.0, unicorn 2.1.4 and lief 1.0.0.

## Alternatives considered

- Separate `requirements/*.in` files compiled with `pip-compile` or `uv pip compile`: two places to declare dependencies.
- `uv` project management (`uv.lock`, `uv sync`): good, but the owner standardised on conda for the interpreter; may be revisited.
- conda-forge for all packages: several packages (langgraph, anthropic, google-genai) lag or are missing there.
