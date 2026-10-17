"""NASM dialect adapter (architecture §12).

Handles the ``nasm`` dialect (Intel syntax, macro assembler).

Phase 0 target: ELF64 Linux SysV (D-021).  Other formats (ELF32, Win64)
are listed in :data:`_NASM_FORMAT_FLAGS` for completeness and will be
exercised in later phases.
"""

from __future__ import annotations

from barthelona.domain.enums import ObjFormat
from barthelona.domain.verification import Diagnostic
from barthelona.toolchains._diagnostics import parse_assembler_output

_NASM_FORMAT_FLAGS: dict[ObjFormat, str] = {
    ObjFormat.ELF64: "elf64",
    ObjFormat.ELF32: "elf32",
    ObjFormat.WIN64: "win64",
    ObjFormat.BIN: "bin",
}


class NasmAdapter:
    """Builds NASM commands and stubs diagnostics parsing (Phase 0)."""

    @property
    def dialect_name(self) -> str:
        return "nasm"

    @property
    def file_extension(self) -> str:
        return ".asm"

    def syntax_check_argv(self, source: str) -> tuple[str, ...]:
        """V0: syntax-only pass; output discarded via ``/dev/null`` inside the container."""
        return ("nasm", "-o", "/dev/null", source)

    def assemble_argv(
        self,
        source: str,
        output: str,
        obj_format: ObjFormat = ObjFormat.ELF64,
    ) -> tuple[str, ...]:
        """V1: assemble *source* to *output* in the requested format."""
        fmt = _NASM_FORMAT_FLAGS.get(obj_format, "elf64")
        return ("nasm", "-f", fmt, "-o", output, source)

    def parse_diagnostics(
        self,
        stdout: bytes,
        stderr: bytes,
        source: str,
    ) -> list[Diagnostic]:  # NOSONAR S1172: stdout and source are part of the Protocol signature
        return parse_assembler_output("nasm", stderr)
