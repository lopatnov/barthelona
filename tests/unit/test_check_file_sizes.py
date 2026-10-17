"""The code-size checker counts code lines only and applies the soft/hard limits."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_file_sizes.py"
_spec = importlib.util.spec_from_file_location("check_file_sizes", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
checker = importlib.util.module_from_spec(_spec)
sys.modules["check_file_sizes"] = checker
_spec.loader.exec_module(checker)


def test_blank_comment_and_docstring_lines_are_free() -> None:
    source = (
        '"""Module docstring\n'
        "spanning lines.\n"
        '"""\n'
        "\n"
        "# a comment\n"
        "def f() -> int:\n"
        '    """Doc."""\n'
        "    x = 1  # trailing comment\n"
        "    return x\n"
    )
    assert checker.count_code_lines(source) == 3


def test_multiline_statement_counts_every_line() -> None:
    assert checker.count_code_lines("x = [\n    1,\n    2,\n]\n") == 4


def test_non_docstring_string_statement_counts() -> None:
    assert checker.count_code_lines('x = 1\n"not a docstring"\n') == 2


def _write(tmp_path: Path, lines: int) -> Path:
    path = tmp_path / "big.py"
    path.write_text("".join(f"x{i} = {i}\n" for i in range(lines)), encoding="utf-8")
    return path


def test_under_soft_limit_is_silent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main(["--soft", "5", "--hard", "8", str(_write(tmp_path, 5))]) == 0
    assert capsys.readouterr().out == ""


def test_over_soft_limit_warns_but_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main(["--soft", "5", "--hard", "8", str(_write(tmp_path, 6))]) == 0
    assert "warning" in capsys.readouterr().out


def test_over_hard_limit_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main(["--soft", "5", "--hard", "8", str(_write(tmp_path, 9))]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_repository_sources_are_within_the_hard_limit() -> None:
    root = _SCRIPT.parents[1]
    assert checker.main([str(root / "src"), str(root / "scripts")]) == 0
