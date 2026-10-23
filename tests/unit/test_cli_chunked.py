"""The ``chunked run`` command: argument validation and the exit code when no model answers."""

from __future__ import annotations

from typer.testing import CliRunner

from barthelona.cli import app

runner = CliRunner()


def test_chunk_settings_outside_the_engine_range_are_rejected() -> None:
    result = runner.invoke(app, ["chunked", "run", "task", "--chunk-tokens", "1000"])
    assert result.exit_code == 2


def test_unknown_profile_stops_without_a_model_and_exits_non_zero() -> None:
    result = runner.invoke(app, ["chunked", "run", "task", "--profile", "does-not-exist"])
    assert result.exit_code != 0
