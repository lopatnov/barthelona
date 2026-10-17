# bart-run: ephemeral sandbox for generated binaries and C harnesses
# (architecture section 13.4, invariant 2). Runtime only: no compilers or
# network at run time; the WSL agent adds the sandbox flags.
# Build: docker build -t bart-run docker/runner
FROM ubuntu:26.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils \
    && rm -rf /var/lib/apt/lists/*

USER 65534:65534
WORKDIR /work
