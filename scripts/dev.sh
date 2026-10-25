#!/usr/bin/env bash
# Run one command with the barthelona conda env on PATH, without activating it. .env is loaded only with the
# opt-in -LoadEnv first argument (D-057): each KEY=VALUE line that is not already set is exported to this one
# command; the values are never printed. Bash twin of scripts/dev.ps1 for agent tool shells and CI.
# Usage: scripts/dev.sh [-LoadEnv] <command> [args...]      e.g. scripts/dev.sh ruff check .
set -euo pipefail

load_env=0
if [[ "${1:-}" = "-LoadEnv" ]]; then
  load_env=1
  shift
fi
if [[ $# -eq 0 ]]; then
  echo "usage: scripts/dev.sh [-LoadEnv] <command> [args...]" >&2
  exit 2
fi

prefix=""
if [[ -n "${CONDA_PREFIX:-}" ]] && [[ "$(basename "$CONDA_PREFIX")" = "barthelona" ]]; then prefix="$CONDA_PREFIX"; fi
if [[ -z "$prefix" ]] && [[ -n "${BARTHELONA_ENV_PREFIX:-}" ]]; then prefix="$BARTHELONA_ENV_PREFIX"; fi
if [[ -z "$prefix" ]]; then
  for c in "${USERPROFILE:-$HOME}/miniconda3/envs/barthelona" "$HOME/miniconda3/envs/barthelona" "${USERPROFILE:-$HOME}/anaconda3/envs/barthelona"; do
    if [[ -x "$c/python.exe" ]] || [[ -x "$c/bin/python" ]]; then prefix="$c"; break; fi
  done
fi
if [[ -z "$prefix" ]]; then
  conda_exe="${CONDA_EXE:-$(command -v conda || true)}"
  if [[ -n "$conda_exe" ]]; then
    prefix="$("$conda_exe" env list 2>/dev/null | awk '$1 == "barthelona" {print $NF}' | head -n 1)"
  fi
fi
if [[ -z "$prefix" ]]; then
  echo "barthelona env not found. Create it with scripts/create_env.sh (or .\\scripts\\create_env.ps1)" >&2
  exit 3
fi

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    p="$(cygpath -u "$prefix" 2>/dev/null || echo "$prefix")"
    export PATH="$p:$p/Scripts:$p/Library/bin:$PATH" ;;
  *)
    export PATH="$prefix/bin:$PATH" ;;
esac
export PYTHONUTF8=1 WSL_UTF8=1
# The env's editable install points at one checkout only; this checkout's src comes first (#268).
src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/src"
sep=":"
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) src_dir="$(cygpath -m "$src_dir")"; sep=";" ;; esac
export PYTHONPATH="$src_dir${PYTHONPATH:+$sep$PYTHONPATH}"

if [[ "$load_env" = 1 ]]; then
  env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
  if [[ ! -f "$env_file" ]]; then
    echo "-LoadEnv: no .env file in the repository root" >&2
    exit 4
  fi
  pattern='^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$'
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ $pattern ]] || continue
    name="${BASH_REMATCH[2]}"
    value="${BASH_REMATCH[3]%"${BASH_REMATCH[3]##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 && ( ( "${value:0:1}" = '"' && "${value: -1}" = '"' ) || ( "${value:0:1}" = "'" && "${value: -1}" = "'" ) ) ]]; then
      value="${value:1:${#value}-2}"
    fi
    if [[ -n "$value" && ! -v $name ]]; then
      export "$name=$value"
    fi
  done < "$env_file"
fi
exec "$@"
