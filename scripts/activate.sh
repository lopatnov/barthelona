# shellcheck shell=bash
# Activate the 'barthelona' conda environment in the CURRENT bash shell.
# Must be sourced:   source scripts/activate.sh [ENV_NAME]
# Bash twin of scripts/activate.ps1 (Git Bash on Windows, or Linux with conda).
# Loads KEY=VALUE lines from <repo>/.env without executing it and never prints values.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "This script must be sourced:  source scripts/activate.sh" >&2
  exit 1
fi

# Activate a conda environment in the current shell, set project endpoint defaults,
# and load literal KEY=VALUE entries from the repo's .env without executing them.
# Arguments: optional environment name (default: barthelona).
# Prints activation status and loaded variable names, never their values.
# Returns: 0 on success, 1 if conda is unavailable or activation fails.
_bart_main() {
  local name="${1:-barthelona}"
  local root conda line key val loaded=""
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  conda="${CONDA_EXE:-$(command -v conda || true)}"
  if [ -z "$conda" ]; then
    echo "conda not found. Install Miniconda or put conda on PATH." >&2
    return 1
  fi
  if ! type conda 2>/dev/null | grep -q 'function'; then
    eval "$("$conda" shell.bash hook)" || return 1
  fi
  conda activate "$name" || { echo "Could not activate '$name'. Create it first: scripts/create_env.sh" >&2; return 1; }

  export PYTHONUTF8=1 WSL_UTF8=1 BARTHELONA_HOME="$root"
  export LMSTUDIO_BASE_URL="${LMSTUDIO_BASE_URL:-http://127.0.0.1:1234/v1}"
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
  export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6343}"

  if [ -f "$root/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%$'\r'}"
      line="${line#$'\xEF\xBB\xBF'}"
      line="${line#"${line%%[![:space:]]*}"}"
      case "$line" in ''|'#'*) continue ;; esac
      line="${line#export }"
      case "$line" in *=*) ;; *) continue ;; esac
      key="${line%%=*}"; key="${key%"${key##*[![:space:]]}"}"
      val="${line#*=}"; val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
      [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
      case "$val" in
        \"*) val="${val#\"}"; val="${val%%\"*}" ;;        # quoted: keep up to the closing quote
        \'*) val="${val#\'}"; val="${val%%\'*}" ;;
        *) val="${val%% \#*}" ;;                           # unquoted: drop an inline ' #' comment
      esac
      [ -n "$val" ] || continue
      export "$key=$val"
      loaded="$loaded $key"
    done < "$root/.env"
  fi

  echo "barthelona env active: $(python -c 'import sys; print(sys.version.split()[0])')  (BARTHELONA_HOME=$root)"
  [ -n "$loaded" ] && echo ".env loaded:$loaded"
  return 0
}

_bart_main "$@"
set -- "$?"
unset -f _bart_main
return "$1"
