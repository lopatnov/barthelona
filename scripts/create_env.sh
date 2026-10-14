#!/usr/bin/env bash
# Create or update the 'barthelona' conda environment and install the hash-locked dependencies.
# Bash twin of scripts/create_env.ps1, for Git Bash on Windows or a Linux host with conda.
# (The WSL VM used for toolchains does not need conda; see docs/runbook.md.)
#
# Usage: scripts/create_env.sh [dev|runtime] [--recreate] [--name NAME]
set -euo pipefail

usage() { sed -n '2,6p' "$0"; exit "${1:-0}"; }

DEPS=dev
RECREATE=0
NAME=barthelona
while [[ $# -gt 0 ]]; do
  case "$1" in
    dev|runtime) DEPS="$1" ;;
    --recreate) RECREATE=1 ;;
    --name) shift; NAME="${1:?--name needs a value}" ;;
    -h|--help) usage 0 ;;
    *) echo "unknown argument: $1" >&2; usage 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA="${CONDA_EXE:-$(command -v conda || true)}"
if [[ -z "$CONDA" ]]; then
  echo "conda not found. Install Miniconda or put conda on PATH." >&2
  exit 1
fi

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PLAT=win ;;
  Linux) PLAT=linux ;;
  *) echo "unsupported platform: $(uname -s)" >&2; exit 1 ;;
esac

LOCK="$REPO_ROOT/requirements/$DEPS.$PLAT.lock"
[[ -f "$LOCK" ]] || { echo "lock file not found: $LOCK (run scripts/lock.ps1)" >&2; exit 1; }

env_exists() { "$CONDA" env list | awk '{print $1}' | grep -qx "$NAME"; }

if env_exists && [[ "$RECREATE" -eq 1 ]] && [[ "$(basename "${CONDA_PREFIX:-}")" = "$NAME" ]]; then
  echo "Environment '$NAME' is active in this shell. Run 'conda deactivate' (or use a new terminal), then retry --recreate." >&2
  exit 1
fi
if env_exists && [[ "$RECREATE" -eq 1 ]]; then
  echo "Removing environment '$NAME'..."
  "$CONDA" env remove --name "$NAME" --yes
fi

if env_exists; then
  echo "Updating environment '$NAME' from environment.yml..."
  "$CONDA" env update --name "$NAME" --file "$REPO_ROOT/environment.yml" --prune
else
  echo "Creating environment '$NAME' from environment.yml..."
  "$CONDA" env create --name "$NAME" --file "$REPO_ROOT/environment.yml"
fi

run_in_env() { "$CONDA" run --no-capture-output --name "$NAME" "$@"; }

cd "$REPO_ROOT"
echo "Installing locked dependencies from requirements/$DEPS.$PLAT.lock..."
run_in_env python -m pip install --disable-pip-version-check --no-warn-script-location --require-hashes --no-deps -r "requirements/$DEPS.$PLAT.lock"
# Updates must leave the env exactly as the lock says (e.g. switching dev -> runtime).
echo "Removing packages that are not in the lock..."
run_in_env python scripts/prune_env.py "requirements/$DEPS.$PLAT.lock"
# --require-hashes cannot be combined with an editable install, so the package goes in a separate step.
echo "Installing barthelona (editable, no deps)..."
run_in_env python -m pip install --disable-pip-version-check --no-warn-script-location --no-deps -e .
run_in_env python -m pip check

echo
echo "Environment '$NAME' is ready (deps: $DEPS). Activate it with:  source scripts/activate.sh"
