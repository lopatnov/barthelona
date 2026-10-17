#!/usr/bin/env bash
# Build bart-tc and bart-run, assemble and link a fixture in the toolchain image,
# then run it under the bart-run sandbox flags. Used by CI and for manual checks
# in WSL. Generated code only ever runs inside the sandboxed container.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
chmod 0777 "$work"
cp "$root/tests/fixtures/smoke/hello_linux64.asm" "$work/"

docker build -q -t bart-tc "$root/docker/toolchain"
docker build -q -t bart-run "$root/docker/runner"

tc=(docker run --rm --network none --read-only --cap-drop ALL
    --security-opt no-new-privileges --tmpfs /tmp:size=16m
    -v "$work:/work" bart-tc)
"${tc[@]}" nasm -f elf64 -o hello.o hello_linux64.asm
"${tc[@]}" ld -o hello hello.o

run=(docker run --rm --network none --read-only --cap-drop ALL
    --security-opt no-new-privileges --user 65534:65534
    --memory 256m --memory-swap 256m --pids-limit 64 --cpus 1
    --ulimit nofile=64 --ulimit fsize=16777216
    --tmpfs /tmp:size=16m -v "$work:/work:ro" bart-run)
out="$("${run[@]}" timeout -s KILL 10 /work/hello)"
[[ "$out" = "ok" ]] || { echo "unexpected output: $out" >&2; exit 1; }
echo "docker smoke test passed"
