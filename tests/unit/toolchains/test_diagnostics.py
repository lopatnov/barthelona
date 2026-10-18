"""Diagnostic parsers replayed against real captured tool output (AGENTS.md testing policy)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from barthelona.domain.verification import Severity
from barthelona.toolchains._diagnostics import parse_assembler_output
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


@pytest.mark.parametrize(
    ("fixture", "text"),
    [("no_prefix_error", "can't open"), ("no_prefix_fatal", "can't create")],
)
def test_gas_error_without_location_is_fatal(fixture: str, text: str) -> None:
    (diag,) = GasAttAdapter().parse_diagnostics(b"", _stderr("as", "2.42", fixture), "x.s")
    assert diag.severity is Severity.FATAL
    assert text in diag.message
    assert diag.file is None
    assert diag.line is None


@given(st.binary(max_size=400))
def test_parser_never_raises_on_arbitrary_bytes(data: bytes) -> None:
    for diag in parse_assembler_output("nasm", data):
        assert diag.message


@given(
    name=st.from_regex(r"[A-Za-z0-9_]{1,12}\.(asm|s)", fullmatch=True),
    line=st.integers(min_value=1, max_value=10**6),
    text=st.from_regex(r"[a-z][a-z ]{0,30}[a-z]", fullmatch=True),
)
def test_well_formed_line_round_trips(name: str, line: int, text: str) -> None:
    (diag,) = parse_assembler_output("nasm", f"{name}:{line}: error: {text}".encode())
    assert (diag.file, diag.line, diag.message, diag.severity) == (name, line, text, Severity.FATAL)


def test_unparseable_output_yields_nothing() -> None:
    assert NasmAdapter().parse_diagnostics(b"", b"Assembler messages:\nsomething odd\n", "x.asm") == []
