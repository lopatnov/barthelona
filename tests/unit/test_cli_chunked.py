"""The ``chunked run`` command: argument validation and the exit code when no model answers."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.llm import FakeGateway
from barthelona.llm.markovian import CHECKPOINT, COMPLETE
from barthelona.llm.runlog import RunLog
from barthelona.verification.asm_gate import AssembleResult

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


def test_stats_are_saved_and_printed_by_the_stats_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\n_start:\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    db = tmp_path / "runs.sqlite"
    run = runner.invoke(app, ["chunked", "run", "write hello", "--code", "--stats", str(db)])
    assert run.exit_code == 0, run.output
    assert "stats: run 1 saved" in run.output
    shown = runner.invoke(app, ["chunked", "stats", "--db", str(db)])
    assert shown.exit_code == 0, shown.output
    assert shown.output.count("┏") == 2  # the runs table and the per-model table; cells are cut at test width
    log = RunLog(db)
    assert [row.label for row in log.last_runs()] == ["write hello"]
    log.close()


def _stub_assemble(monkeypatch: pytest.MonkeyPatch, *results: AssembleResult) -> list[str]:
    queue, seen = list(results), []

    def fake(source: str, nasm: str | None = None) -> AssembleResult:
        seen.append(source)
        return queue.pop(0)

    monkeypatch.setattr("barthelona.cli.chunked.assemble_source", fake)
    return seen


_STATE = "COMPLETED: all. REMAINING: nothing. DECISIONS: use sys_write then sys_exit on Linux x86-64."


def test_assemble_failure_exits_non_zero_and_keeps_the_memory_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\nbad\n```\n{CHECKPOINT}\n{_STATE}", f"x\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("fail", ("line 1: bad",)))
    memory = tmp_path / "mem.sqlite"
    result = runner.invoke(app, ["chunked", "run", "t", "--assemble", "--memory", str(memory)])
    assert result.exit_code == 1
    assert "written=0 (assemble oracle: fail)" in result.output
    assert "assemble: fail" in result.output


def test_repair_feeds_nasm_errors_back_and_green_needs_the_second_attempt_to_assemble(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\nbad\n```\n{COMPLETE}", f"```asm\ngood\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    seen = _stub_assemble(monkeypatch, AssembleResult("fail", ("line 1: bad",)), AssembleResult("pass"))
    db, out = tmp_path / "runs.sqlite", tmp_path / "hello.asm"
    result = runner.invoke(
        app, ["chunked", "run", "t", "--assemble", "--repair", "1", "--stats", str(db), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert seen == ["bad", "good"]
    assert "line 1: bad" in fake.calls[1][1].messages[1].content
    assert out.read_text(encoding="utf-8") == "good\n"
    log = RunLog(db)
    assert [row.label for row in log.last_runs()] == ["t [repair 1]", "t"]
    log.close()


def test_an_unavailable_assembler_is_not_a_pass_and_is_not_called_a_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\nx\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("unavailable", ("nasm was not found",)))
    result = runner.invoke(app, ["chunked", "run", "t", "--assemble", "--memory", str(tmp_path / "m.sqlite")])
    assert result.exit_code == 1
    assert "written=0 (assemble oracle: unavailable)" in result.output


def test_the_nasm_path_can_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGateway([f"```asm\nx\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    paths: list[str | None] = []

    def record(source: str, nasm: str | None = None) -> AssembleResult:
        paths.append(nasm)
        return AssembleResult("pass")

    monkeypatch.setattr("barthelona.cli.chunked.assemble_source", record)
    monkeypatch.setenv("BARTHELONA_NASM", "C:/tools/nasm.exe")
    assert runner.invoke(app, ["chunked", "run", "t", "--assemble"]).exit_code == 0
    assert paths == ["C:/tools/nasm.exe"]


def test_a_blank_task_is_still_recorded_with_a_placeholder_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\n_start:\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    db = tmp_path / "runs.sqlite"
    result = runner.invoke(app, ["chunked", "run", "  \n ", "--code", "--stats", str(db)])
    assert result.exit_code == 0, result.output
    log = RunLog(db)
    assert [row.label for row in log.last_runs()] == ["(empty task)"]
    log.close()


def test_stats_command_without_a_database_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["chunked", "stats", "--db", str(tmp_path / "none.sqlite")])
    assert result.exit_code == 2


def test_unknown_profile_stops_without_a_model_and_exits_non_zero() -> None:
    result = runner.invoke(app, ["chunked", "run", "task", "--profile", "does-not-exist"])
    assert result.exit_code != 0
