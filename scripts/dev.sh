#!/usr/bin/env bash
# Run one command with the barthelona conda env on PATH, without activating it and without loading .env.
# Bash twin of scripts/dev.ps1 for agent tool shells (Claude Code, Codex) and CI.
# Usage: scripts/dev.sh <command> [args...]      e.g. scripts/dev.sh ruff check .
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: scripts/dev.sh <command> [args...]" >&2
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
exec "$@"
