"""The ``chunked run`` command: argument validation and the exit code when no model answers."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.llm import FakeGateway
from barthelona.llm.markovian import CHECKPOINT, COMPLETE

runner = CliRunner()


def test_chunk_settings_outside_the_engine_range_are_rejected() -> None:
    result = runner.invoke(app, ["chunked", "run", "task", "--chunk-tokens", "1000"])
    assert result.exit_code == 2


def test_plan_review_and_memory_each_reach_their_role(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = "COMPLETED: all. REMAINING: nothing. DECISIONS: use sys_write then sys_exit on Linux x86-64."
    fake = FakeGateway(
        [
            "1. data\n2. text",
            f"```asm\n_start:\n```\n{CHECKPOINT}\n{state}",
            f"x\n{COMPLETE}",
            "looks complete",
        ]
    )
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    out = tmp_path / "hello.asm"
    result = runner.invoke(
        app,
        [
            "chunked", "run", "write hello", "--plan-role", "planner", "--review-role", "cheap",
            "--code", "--memory", str(tmp_path / "mem.sqlite"), "--out", str(out),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert [call[0] for call in fake.calls] == ["planner", "worker", "worker", "cheap"]
    assert "Plan from the planner" in fake.calls[1][1].messages[1].content
    assert out.read_text(encoding="utf-8") == "_start:\n"
    assert "written=1" in result.output and "advisory" in result.output


def test_code_flag_refuses_an_answer_without_code_and_keeps_the_raw_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"only prose here\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    out = tmp_path / "hello.asm"
    result = runner.invoke(app, ["chunked", "run", "write hello", "--code", "--out", str(out)])
    assert result.exit_code == 1
    assert not out.exists()
    assert "only prose here" in (tmp_path / "hello.asm.raw.txt").read_text(encoding="utf-8")


def test_unknown_profile_stops_without_a_model_and_exits_non_zero() -> None:
    result = runner.invoke(app, ["chunked", "run", "task", "--profile", "does-not-exist"])
    assert result.exit_code != 0
