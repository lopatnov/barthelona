"""Diagnostic parsers replayed against real captured tool output (AGENTS.md testing policy)."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.domain.verification import Severity
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.toolchains.gas import GasAttAdapter, GasIntelAdapter
from barthelona.toolchains.nasm import NasmAdapter

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "diagnostics"


def _stderr(tool: str, version: str, name: str) -> bytes:
    return (_FIXTURES / tool / version / f"{name}.stderr").read_bytes()


# (adapter, tool, version, fixture, [(line, severity, message-substring)])
_CASES = [
    (
        NasmAdapter(),
        "nasm",
        "2.16.01",
        "syntax_error",
        [(5, Severity.FATAL, "instruction expected"), (6, Severity.FATAL, "expression syntax error")],
    ),
    (
        NasmAdapter(),
        "nasm",
        "2.16.01",
        "undefined_symbol_and_operands",
        [(4, Severity.FATAL, "not defined"), (5, Severity.FATAL, "invalid combination")],
    ),
    (NasmAdapter(), "nasm", "2.16.01", "warning", [(5, Severity.WARNING, "byte data exceeds bounds")]),
    (
        GasAttAdapter(),
        "as",
        "2.42",
        "att_errors",
        [(5, Severity.FATAL, "no such instruction"), (6, Severity.FATAL, "operands mismatch")],
    ),
    (GasIntelAdapter(), "as", "2.42", "warning", [(5, Severity.WARNING, "truncated")]),
]


@pytest.mark.parametrize(("adapter", "tool", "version", "fixture", "expected"), _CASES)
def test_parses_captured_output(
    adapter: DialectAdapter,
    tool: str,
    version: str,
    fixture: str,
    expected: list[tuple[int, Severity, str]],
) -> None:
    diagnostics = adapter.parse_diagnostics(b"", _stderr(tool, version, fixture), "ignored.asm")
    assert [(d.line, d.severity) for d in diagnostics] == [(line, sev) for line, sev, _ in expected]
    for d, (_, _, text) in zip(diagnostics, expected, strict=True):
        assert text in d.message
        assert d.tool == tool
        assert d.file is not None
        assert d.error_sig is not None


def test_nasm_warning_class_becomes_code() -> None:
    (diag,) = NasmAdapter().parse_diagnostics(b"", _stderr("nasm", "2.16.01", "warning"), "warning.asm")
    assert diag.code == "-w+number-overflow"
    assert "[-w" not in diag.message


def test_error_signature_ignores_numbers_and_symbols() -> None:
    a = NasmAdapter().parse_diagnostics(b"", b"x.asm:3: error: symbol `foo' not defined", "x.asm")
    b = NasmAdapter().parse_diagnostics(b"", b"y.asm:99: error: symbol `bar' not defined", "y.asm")
    assert a[0].error_sig == b[0].error_sig


def test_unparseable_output_yields_nothing() -> None:
    assert NasmAdapter().parse_diagnostics(b"", b"Assembler messages:\nsomething odd\n", "x.asm") == []
