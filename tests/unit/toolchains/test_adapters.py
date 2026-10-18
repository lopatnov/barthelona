"""Unit tests for NasmAdapter, GasIntelAdapter and GasAttAdapter."""

from __future__ import annotations

import pytest

from barthelona.domain.enums import ObjFormat
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.toolchains.gas import GasAttAdapter, GasIntelAdapter
from barthelona.toolchains.nasm import NasmAdapter

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "adapter",
    [NasmAdapter(), GasIntelAdapter(), GasAttAdapter()],
    ids=["nasm", "gas-intel", "gas-att"],
)
def test_is_dialect_adapter(adapter: object) -> None:
    assert isinstance(adapter, DialectAdapter)


@pytest.mark.parametrize(
    "adapter",
    [NasmAdapter(), GasIntelAdapter(), GasAttAdapter()],
    ids=["nasm", "gas-intel", "gas-att"],
)
def test_include_path_is_the_source_directory(adapter: DialectAdapter) -> None:
    """#122: ``docker exec`` starts in /work, so ``gen/x.inc`` needs ``-I <session dir>/``."""
    source = "/cache/runs/r1/a1/main.asm"
    for argv in (adapter.syntax_check_argv(source), adapter.assemble_argv(source, "/cache/runs/r1/a1/main.o")):
        assert argv[argv.index("-I") + 1] == "/cache/runs/r1/a1/"


# ---------------------------------------------------------------------------
# NasmAdapter
# ---------------------------------------------------------------------------


class TestNasmAdapter:
    def setup_method(self) -> None:
        self.a = NasmAdapter()

    def test_dialect_name(self) -> None:
        assert self.a.dialect_name == "nasm"

    def test_file_extension(self) -> None:
        assert self.a.file_extension == ".asm"

    def test_syntax_check_argv_starts_with_nasm(self) -> None:
        argv = self.a.syntax_check_argv("hello.asm")
        assert argv[0] == "nasm"

    def test_syntax_check_argv_discards_output(self) -> None:
        argv = self.a.syntax_check_argv("hello.asm")
        assert "/dev/null" in argv

    def test_syntax_check_argv_includes_source(self) -> None:
        argv = self.a.syntax_check_argv("hello.asm")
        assert "hello.asm" in argv

    def test_syntax_check_uses_the_elf_format_so_extern_is_accepted(self) -> None:
        argv = self.a.syntax_check_argv("hello.asm")
        assert argv[argv.index("-f") + 1] == "elf64"

    def test_assemble_argv_elf64(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "hello.o", ObjFormat.ELF64)
        assert argv[0] == "nasm"
        assert "-f" in argv
        elf_idx = argv.index("-f")
        assert argv[elf_idx + 1] == "elf64"

    def test_assemble_argv_elf32(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "hello.o", ObjFormat.ELF32)
        assert "elf32" in argv

    def test_assemble_argv_win64(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "hello.o", ObjFormat.WIN64)
        assert "win64" in argv

    def test_assemble_argv_bin(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "hello.o", ObjFormat.BIN)
        assert "bin" in argv

    def test_assemble_argv_default_format_is_elf64(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "hello.o")
        assert "elf64" in argv

    def test_assemble_argv_includes_output(self) -> None:
        argv = self.a.assemble_argv("hello.asm", "out.o")
        assert "out.o" in argv

    def test_parse_diagnostics_stub_returns_empty(self) -> None:
        assert self.a.parse_diagnostics(b"", b"error: something", "hello.asm") == []


# ---------------------------------------------------------------------------
# GasIntelAdapter
# ---------------------------------------------------------------------------


class TestGasIntelAdapter:
    def setup_method(self) -> None:
        self.a = GasIntelAdapter()

    def test_dialect_name(self) -> None:
        assert self.a.dialect_name == "gas-intel"

    def test_file_extension(self) -> None:
        assert self.a.file_extension == ".s"

    def test_syntax_check_argv_uses_intel_flags(self) -> None:
        argv = self.a.syntax_check_argv("hello.s")
        assert "-msyntax=intel" in argv
        assert "-mnaked-reg" in argv

    def test_syntax_check_argv_discards_output(self) -> None:
        argv = self.a.syntax_check_argv("hello.s")
        assert "/dev/null" in argv

    def test_assemble_argv_elf64_arch_flag(self) -> None:
        argv = self.a.assemble_argv("hello.s", "hello.o", ObjFormat.ELF64)
        assert "--64" in argv

    def test_assemble_argv_elf32_arch_flag(self) -> None:
        argv = self.a.assemble_argv("hello.s", "hello.o", ObjFormat.ELF32)
        assert "--32" in argv

    def test_assemble_argv_retains_intel_flags(self) -> None:
        argv = self.a.assemble_argv("hello.s", "hello.o")
        assert "-msyntax=intel" in argv
        assert "-mnaked-reg" in argv

    def test_parse_diagnostics_stub_returns_empty(self) -> None:
        assert self.a.parse_diagnostics(b"", b"", "hello.s") == []


# ---------------------------------------------------------------------------
# GasAttAdapter
# ---------------------------------------------------------------------------


class TestGasAttAdapter:
    def setup_method(self) -> None:
        self.a = GasAttAdapter()

    def test_dialect_name(self) -> None:
        assert self.a.dialect_name == "gas-att"

    def test_file_extension(self) -> None:
        assert self.a.file_extension == ".s"

    def test_syntax_check_argv_no_intel_flags(self) -> None:
        argv = self.a.syntax_check_argv("hello.s")
        assert "-msyntax=intel" not in argv
        assert "-mnaked-reg" not in argv

    def test_syntax_check_argv_starts_with_as(self) -> None:
        argv = self.a.syntax_check_argv("hello.s")
        assert argv[0] == "as"

    def test_assemble_argv_elf64_arch_flag(self) -> None:
        argv = self.a.assemble_argv("hello.s", "hello.o", ObjFormat.ELF64)
        assert "--64" in argv

    def test_assemble_argv_no_intel_flags(self) -> None:
        argv = self.a.assemble_argv("hello.s", "hello.o")
        assert "-msyntax=intel" not in argv

    def test_parse_diagnostics_stub_returns_empty(self) -> None:
        assert self.a.parse_diagnostics(b"", b"", "hello.s") == []
