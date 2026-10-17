# bart-tc: long-lived toolchain container (architecture section 12, D-006).
# Assemblers, linkers and compilers only; generated binaries never run here.
# Build: docker build -t bart-tc docker/toolchain
FROM ubuntu:26.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils gcc gdb libc6-dev make nasm yasm \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for tool runs (uid 1000 is the image's built-in `ubuntu` user);
# the WSL agent mounts only the staged project.
USER 1000:1000
WORKDIR /work
CMD ["sleep", "infinity"]
