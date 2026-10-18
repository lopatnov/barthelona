"""``verify --require`` decides the exit code from the required levels (#123)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.cli._report import exit_code
from barthelona.domain import Level, LevelResult

runner = CliRunner()


def _result(level: Level, status: str) -> LevelResult:
    return LevelResult(level=level, status=status, secs=0.0)  # type: ignore[arg-type]  # valid literal


_MVP = {Level.V0, Level.V1, Level.V2, Level.V5, Level.V6}
_GREEN_MVP = [
    _result(Level.V0, "pass"),
    _result(Level.V1, "pass"),
    _result(Level.V2, "pass"),
    _result(Level.V3, "unsupported"),
    _result(Level.V4, "unsupported"),
    _result(Level.V5, "pass"),
    _result(Level.V6, "pass"),
]


def test_unsupported_levels_fail_the_run_by_default() -> None:
    assert exit_code(_GREEN_MVP) == 1


def test_unsupported_levels_outside_the_required_set_do_not_fail() -> None:
    assert exit_code(_GREEN_MVP, _MVP) == 0


def test_an_unsupported_required_level_fails() -> None:
    assert exit_code(_GREEN_MVP, {*_MVP, Level.V3}) == 1


def test_any_failed_level_fails_even_outside_the_required_set() -> None:
    results = [*_GREEN_MVP[:3], _result(Level.V3, "fail")]
    assert exit_code(results, {Level.V0}) == 1


@pytest.mark.parametrize("require", ["V9", "", "V0,V6"])
def test_require_rejects_bad_values(tmp_path: Path, require: str) -> None:
    (tmp_path / "a.asm").write_text("; stub\n", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(tmp_path), "--level", "V2", "--require", require])
    assert result.exit_code == 2
