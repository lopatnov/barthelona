# bart-tc: long-lived toolchain container (architecture section 12, D-006).
# Assemblers, linkers and compilers only; generated binaries never run here.
# Build: docker build -t bart-tc docker/toolchain
FROM ubuntu:26.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils gcc libc6-dev make nasm yasm gdb \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for tool runs; the WSL agent mounts only the staged project.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin bart
USER 1000:1000
WORKDIR /work
CMD ["sleep", "infinity"]
