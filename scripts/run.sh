#!/usr/bin/env bash
# scripts/run.sh — Launches the barthelona worker and Streamlit UI (Linux/WSL version)
#
# Starts the worker process (which claims queued runs and drives the engine graph)
# and the Streamlit UI (New Request, Approvals, Live Run pages) in parallel.
# Both processes share the same SQLite database (var/app.sqlite) for coordination.
#
# Usage: ./scripts/run.sh [--worker-only] [--ui-only] [--port 8501]

set -euo pipefail

DB_PATH="var/app.sqlite"
CHECKPOINTS_PATH="var/checkpoints.sqlite"
RUNS_PATH="var/runs"
CATALOG_PATH="config/models.yaml"
FACTS_SQL=""
POLL_INTERVAL=1.0
WORKER_ONLY=false
UI_ONLY=false
STREAMLIT_PORT=8501

while [[ $# -gt 0 ]]; do
    case $1 in
        --db) DB_PATH="$2"; shift 2 ;;
        --checkpoints) CHECKPOINTS_PATH="$2"; shift 2 ;;
        --runs) RUNS_PATH="$2"; shift 2 ;;
        --catalog) CATALOG_PATH="$2"; shift 2 ;;
        --facts-sql) FACTS_SQL="$2"; shift 2 ;;
        --poll) POLL_INTERVAL="$2"; shift 2 ;;
        --worker-only) WORKER_ONLY=true; shift ;;
        --ui-only) UI_ONLY=true; shift ;;
        --port) STREAMLIT_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure we run from the repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate the conda environment for this command only
ENV_SCRIPT="./scripts/dev.sh"
if [[ ! -f "$ENV_SCRIPT" ]]; then
    echo "Environment script not found: $ENV_SCRIPT" >&2
    exit 1
fi

# Create required directories
mkdir -p var var/runs workspaces

WORKER_PID=""
UI_PID=""
PIDS=()

cleanup() {
    echo "Stopping processes..." >&2
    [[ -n "$WORKER_PID" ]] && kill "$WORKER_PID" 2>/dev/null || true
    [[ -n "$UI_PID" ]] && kill "$UI_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
    wait "$UI_PID" 2>/dev/null || true
    echo "Stopped." >&2
}

trap cleanup EXIT INT TERM

start_worker() {
    local args=(
        python -m barthelona worker
        --db "$DB_PATH"
        --checkpoints "$CHECKPOINTS_PATH"
        --runs "$RUNS_PATH"
        --catalog "$CATALOG_PATH"
        --poll "$POLL_INTERVAL"
    )
    [[ -n "$FACTS_SQL" ]] && args+=(--facts-sql "$FACTS_SQL")

    echo "Starting worker: ${args[*]}" >&2
    PYTHONPATH=src "$ENV_SCRIPT" "${args[@]}" &
    WORKER_PID=$!
    PIDS+=("$WORKER_PID")
}

start_ui() {
    local args=(
        streamlit run src/barthelona/ui/app.py
        --server.port "$STREAMLIT_PORT"
        --server.headless true
        --browser.gatherUsageStats false
    )

    echo "Starting Streamlit UI: ${args[*]}" >&2
    PYTHONPATH=src "$ENV_SCRIPT" "${args[@]}" &
    UI_PID=$!
    PIDS+=("$UI_PID")
}

if [[ "$UI_ONLY" != true ]]; then
    start_worker
    sleep 2  # Give worker time to start
fi

if [[ "$WORKER_ONLY" != true ]]; then
    start_ui
fi

echo ""
echo "barthelona is running." >&2
echo "  Worker:  $WORKER_PID" >&2
echo "  Streamlit: $UI_PID on http://127.0.0.1:$STREAMLIT_PORT" >&2
echo ""
echo "Press Ctrl+C to stop both processes." >&2

wait "${PIDS[@]}"