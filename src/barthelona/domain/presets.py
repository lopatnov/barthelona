"""Built-in target presets the UI offers; the toolchain probe decides what is installed, not this list."""

from __future__ import annotations

from barthelona.domain.enums import ABI, OS, Arch, Dialect, Linker, ObjFormat, RunEnv
from barthelona.domain.project import TargetProfile


def _linux_x64(preset: str, dialect: Dialect) -> TargetProfile:
    return TargetProfile(
        preset=preset,
        dialect=dialect,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        pie=False,
        entry="_start",
        run_env=RunEnv.DOCKER_NATIVE,
    )


def builtin_presets() -> list[TargetProfile]:
    return [
        _linux_x64("linux-x64-nasm-static", Dialect.NASM),
        _linux_x64("linux-x64-gas-intel", Dialect.GAS_INTEL),
        _linux_x64("linux-x64-gas-att", Dialect.GAS_ATT),
    ]
