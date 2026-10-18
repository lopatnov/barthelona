#!/usr/bin/env bash
# One-command toolchain setup: build bart-tc and bart-run and start the long-lived
# bart-tc container the agent execs into (D-043). Idempotent; run it in WSL on
# Windows (wsl -d Ubuntu -e bash scripts/setup-toolchain.sh) or on a Linux host.
# Generated code never runs here: bart-tc only assembles and links.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cache="$HOME/.cache/barthelona"
mkdir -p "$cache"

docker build -q -t bart-tc "$root/docker/toolchain"
docker build -q -t bart-run "$root/docker/runner"

if [[ "$(docker inspect --format '{{.State.Running}}' bart-tc 2>/dev/null || true)" != "true" ]]; then
    docker rm -f bart-tc >/dev/null 2>&1 || true
    docker run -d --name bart-tc --restart unless-stopped --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges --tmpfs /tmp:size=16m \
        --user "$(id -u):$(id -g)" -v "$cache:$cache" bart-tc >/dev/null
fi
echo "toolchain ready: bart-tc is running, bart-run is built"
