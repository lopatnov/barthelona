"""GAS dialect adapters — Intel syntax and AT&T syntax (architecture §12).

GAS (GNU Assembler, ``as``) covers both ``gas-intel`` and ``gas-att``
dialects; the only difference is whether ``-msyntax=intel`` is passed.

Phase 0 target: ELF64 Linux SysV (D-021).
"""

from __future__ import annotations

from barthelona.domain.enums import ObjFormat
from barthelona.domain.verification import Diagnostic

_GAS_ARCH_FLAGS: dict[ObjFormat, tuple[str, ...]] = {
    ObjFormat.ELF64: ("--64",),
    ObjFormat.ELF32: ("--32",),
}


class GasIntelAdapter:
    """GAS with Intel syntax (``gas-intel`` dialect)."""

    @property
    def dialect_name(self) -> str:
        return "gas-intel"

    @property
    def file_extension(self) -> str:
        return ".s"

    def syntax_check_argv(self, source: str) -> tuple[str, ...]:
        """V0: syntax-only; output discarded via ``/dev/null`` inside the container."""
        return ("as", "-msyntax=intel", "-mnaked-reg", "-o", "/dev/null", source)

    def assemble_argv(
        self,
        source: str,
        output: str,
        obj_format: ObjFormat = ObjFormat.ELF64,
    ) -> tuple[str, ...]:
        """V1: assemble *source* to *output*."""
        arch_flags = _GAS_ARCH_FLAGS.get(obj_format, ("--64",))
        return ("as", "-msyntax=intel", "-mnaked-reg", *arch_flags, "-o", output, source)

    def parse_diagnostics(
        self,
        stdout: bytes,
        stderr: bytes,
        source: str,
    ) -> list[Diagnostic]:  # NOSONAR S1172: Protocol signature; parameters are used once #46 lands
        # Stub until real tool output is captured as fixtures (AGENTS.md testing policy); tracked in #46.
        return []


class GasAttAdapter:
    """GAS with AT&T syntax (``gas-att`` dialect)."""

    @property
    def dialect_name(self) -> str:
        return "gas-att"

    @property
    def file_extension(self) -> str:
        return ".s"

    def syntax_check_argv(self, source: str) -> tuple[str, ...]:
        """V0: syntax-only; output discarded via ``/dev/null`` inside the container."""
        return ("as", "-o", "/dev/null", source)

    def assemble_argv(
        self,
        source: str,
        output: str,
        obj_format: ObjFormat = ObjFormat.ELF64,
    ) -> tuple[str, ...]:
        """V1: assemble *source* to *output*."""
        arch_flags = _GAS_ARCH_FLAGS.get(obj_format, ("--64",))
        return ("as", *arch_flags, "-o", output, source)

    def parse_diagnostics(
        self,
        stdout: bytes,
        stderr: bytes,
        source: str,
    ) -> list[Diagnostic]:  # NOSONAR S1172: Protocol signature; parameters are used once #46 lands
        # Stub until real tool output is captured as fixtures (AGENTS.md testing policy); tracked in #46.
        return []
