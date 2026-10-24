"""The ``chunked run`` command: argument validation and the exit code when no model answers."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
from barthelona.llm import FakeGateway
from barthelona.llm.markovian import CHECKPOINT, COMPLETE
from barthelona.llm.runlog import RunLog
from barthelona.llm.zetaris import SqlResult
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

    monkeypatch.setattr("barthelona.verification.asm_gate.assemble_source", fake)
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


def test_repair_attempts_can_use_a_stronger_role(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGateway([f"```asm\nbad\n```\n{COMPLETE}", f"```asm\ngood\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("fail", ("line 1: bad",)), AssembleResult("pass"))
    result = runner.invoke(
        app, ["chunked", "run", "t", "--assemble", "--repair", "1", "--repair-role", "planner"]
    )
    assert result.exit_code == 0, result.output
    assert [role for role, _ in fake.calls] == ["worker", "planner"]


def test_a_later_chunk_that_restates_the_program_with_changes_does_not_sink_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = "_start:\n    mov eax, 1\n    xor edi, edi"
    second = "_start:\n    mov eax, 60\n    xor edi, edi"
    fake = FakeGateway(
        [f"```asm\n{first}\n```\n{CHECKPOINT}\n{_STATE}", f"```asm\n{second}\n```\n{COMPLETE}"]
    )
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    seen = _stub_assemble(monkeypatch, AssembleResult("fail", ("redefined",)), AssembleResult("pass"))
    out = tmp_path / "hello.asm"
    result = runner.invoke(app, ["chunked", "run", "t", "--assemble", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert seen == [f"{first}\n{second}", second]
    assert out.read_text(encoding="utf-8") == second + "\n"
    assert "one block alone assembles" in result.output


def test_an_unavailable_assembler_is_not_a_pass_and_is_not_called_a_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\nx\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("unavailable", ("nasm was not found",)))
    result = runner.invoke(app, ["chunked", "run", "t", "--assemble", "--memory", str(tmp_path / "m.sqlite")])
    assert result.exit_code == 1
    assert "written=0 (assemble oracle: unavailable)" in result.output


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


def test_facts_sql_puts_zetaris_rows_in_front_of_the_first_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\n_start:\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    monkeypatch.setenv("ZETARIS_API_KEY", "k")
    monkeypatch.setattr(
        "barthelona.cli.chunked.run_sql", lambda config, sql: SqlResult((("write", "1"), ("exit", "60")))
    )
    result = runner.invoke(app, ["chunked", "run", "t", "--facts-sql", "SELECT name, nr FROM syscalls"])
    assert result.exit_code == 0, result.output
    first = fake.calls[0][1].messages[1].content
    assert "[ZETARIS FACTS] rows of: SELECT name, nr FROM syscalls" in first
    assert "write | 1" in first


def test_facts_sql_without_a_key_stops_instead_of_being_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    result = runner.invoke(app, ["chunked", "run", "t", "--facts-sql", "SELECT 1"])
    assert result.exit_code != 0
    assert "ZETARIS_API_KEY" in result.output


def test_single_shot_mode_bypasses_chunking(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Single-shot mode completes in one call without checkpoint markers."""
    fake = FakeGateway([f"```asm\n_start:\n    mov eax, 60\n    xor edi, edi\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    out = tmp_path / "hello.asm"
    result = runner.invoke(
        app, ["chunked", "run", "write hello", "--single-shot", "--code", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") == "_start:\n    mov eax, 60\n    xor edi, edi\n"
    # Only one call to the worker role (no planner since not specified, no checkpoints)
    assert [call[0] for call in fake.calls] == ["worker"]
    # The output should show only 1 chunk with marker "complete"
    assert "chunks=1" in result.output
    assert "marker=complete" in result.output or "complete" in result.output.lower()


def test_single_shot_with_plan_and_review(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Single-shot mode works with plan and review roles."""
    fake = FakeGateway(
        [
            "1. data\n2. text",  # planner
            f"```asm\n_start:\n```\n{COMPLETE}",  # worker
            "looks complete",  # reviewer
        ]
    )
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    out = tmp_path / "hello.asm"
    result = runner.invoke(
        app,
        [
            "chunked",
            "run",
            "write hello",
            "--plan-role",
            "planner",
            "--review-role",
            "cheap",
            "--single-shot",
            "--code",
            "--out",
            str(out),
            "--memory",
            str(tmp_path / "mem.sqlite"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert [call[0] for call in fake.calls] == ["planner", "worker", "cheap"]
    assert "Plan from the planner" in fake.calls[1][1].messages[1].content
    assert out.read_text(encoding="utf-8") == "_start:\n"
    # Single-shot has no state block, so no facts are written to memory (written=0)
    assert "written=0" in result.output and "advisory" in result.output


def test_single_shot_still_runs_the_assemble_oracle_and_repairs(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGateway([f"```asm\nbad\n```\n{COMPLETE}", f"```asm\ngood\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("fail", ("line 1: bad",)), AssembleResult("pass"))
    result = runner.invoke(
        app,
        ["chunked", "run", "t", "--single-shot", "--assemble", "--repair", "1", "--repair-role", "planner"],
    )
    assert result.exit_code == 0, result.output
    assert [role for role, _ in fake.calls] == ["worker", "planner"]
    assert "assemble: pass" in result.output


def test_single_shot_rejected_by_the_assembler_exits_non_zero_and_writes_no_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\nbad\n```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    _stub_assemble(monkeypatch, AssembleResult("fail", ("line 1: bad",)))
    result = runner.invoke(
        app, ["chunked", "run", "t", "--single-shot", "--assemble", "--memory", str(tmp_path / "m.sqlite")]
    )
    assert result.exit_code == 1
    assert "written=0" in result.output


_HELLO_ASM = (
    'section .data\n    msg db "Hello, Barthelona!", 10\n    msg_len equ $ - msg\nsection .text\n'
    "    global _start\n_start:\n    mov rax, 1\n    mov rdi, 1\n    mov rsi, msg\n    mov rdx, msg_len\n"
    "    syscall\n    mov rax, 60\n    xor rdi, rdi\n    syscall\n"
)
_needs_nasm = pytest.mark.skipif(
    shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it"
)


@_needs_nasm
def test_expect_stdout_runs_the_program_in_the_emulator_and_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\n{_HELLO_ASM}```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    out = tmp_path / "hello.asm"
    args = ["chunked", "run", "t", "--expect-stdout", "Hello, Barthelona!\\n", "--out", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "assemble: pass" in result.output


@_needs_nasm
def test_a_program_that_assembles_but_prints_the_wrong_text_is_repaired_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrong = _HELLO_ASM.replace("msg_len\n", "6\n")
    fake = FakeGateway([f"```asm\n{wrong}```\n{COMPLETE}", f"```asm\n{_HELLO_ASM}```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    args = ["chunked", "run", "t", "--expect-stdout", "Hello, Barthelona!\\n", "--repair", "1"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    repair_prompt = fake.calls[1][1].messages[1].content
    assert "stdout was 'Hello,'" in repair_prompt
    assert "was rejected when it was assembled and run" in repair_prompt


@_needs_nasm
def test_a_wrong_program_without_repair_fails_the_run_and_writes_no_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeGateway([f"```asm\n{_HELLO_ASM.replace('xor rdi, rdi', 'mov rdi, 3')}```\n{COMPLETE}"])
    monkeypatch.setattr("barthelona.cli.chunked.Gateway", lambda *args, **kwargs: fake)
    result = runner.invoke(
        app, ["chunked", "run", "t", "--expect-exit", "0", "--memory", str(tmp_path / "m.db")]
    )
    assert result.exit_code == 1
    assert "exit code was 3, expected 0" in result.output
    assert "written=0" in result.output
