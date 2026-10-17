"""The suite loop, the JSONL results and the comparison report (no model, no toolchain)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.bench import (
    Arm,
    AttemptResult,
    BenchError,
    BenchTask,
    RunSettings,
    TaskResult,
    load_prompts,
    load_suite,
)
from barthelona.bench.report import append_result, format_report, read_results, summarize
from barthelona.bench.suite import run_suite
from barthelona.bench.verifier import adapter_for
from barthelona.cli import app
from barthelona.domain.enums import Dialect, StopReason
from barthelona.domain.verification import LevelResult
from barthelona.llm import FakeGateway
from barthelona.toolchains import GasAttAdapter, NasmAdapter

BENCH = Path(__file__).resolve().parents[3] / "bench"
TASKS = [task for task in load_suite(BENCH, "dev") if task.id in {"gcd", "fib"}]


class _AlwaysGreen:
    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]:  # NOSONAR S7503
        return [LevelResult(level=level, status="pass", secs=0) for level in ("V0", "V1", "V2", "V5")]  # type: ignore[arg-type]


def _result(task: str, arm: str, seed: int, *, green: bool, tok_per_s: float | None = 40.0) -> TaskResult:
    attempt = AttemptResult(number=0, passed=green, tok_per_s=tok_per_s, served_by="lmstudio/m")
    return TaskResult(
        task_id=task,
        arm=arm,
        seed=seed,
        stop_reason=StopReason.GREEN if green else StopReason.MAX_ATTEMPTS,
        attempts=(attempt,),
    )


def test_the_source_name_comes_from_the_contract() -> None:
    assert {task.source_name for task in TASKS} == {"gcd.asm", "fib.asm"}


async def test_every_task_runs_under_every_arm_and_seed() -> None:
    seen: list[TaskResult] = []
    replies = [f"=== FILE: {name}.asm ===\nret\n=== END ===" for name in ("gcd", "gcd", "fib", "fib")] * 2
    results = await run_suite(
        TASKS,
        [Arm("single", 0), Arm("fix", 2)],
        [0, 1],
        FakeGateway(replies),
        _AlwaysGreen(),
        load_prompts(BENCH),
        Path("."),
        RunSettings(),
        seen.append,
    )
    assert len(results) == len(seen) == 2 * 2 * 2
    assert {(r.task_id, r.arm, r.seed) for r in results} == {
        (t.id, a, s) for t in TASKS for a in ("single", "fix") for s in (0, 1)
    }


def test_results_round_trip_through_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "out" / "results.jsonl"
    written = [_result("gcd", "single", 0, green=True), _result("gcd", "fix", 0, green=False)]
    for result in written:
        append_result(path, result)
    assert read_results(path) == written


def test_a_corrupt_results_file_is_a_bench_error(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(BenchError):
        read_results(path)


def test_the_summary_counts_runs_and_green_attempts() -> None:
    results = [_result(f"t{i}", "single", s, green=i < 3) for i in range(4) for s in (0, 1)]
    summary = summarize(results, "single")
    assert (summary.tasks, summary.seeds, summary.runs) == (4, 2, 8)
    assert summary.pass_rate == pytest.approx(0.75)
    assert summary.first_try == pytest.approx(0.75)
    assert summary.attempts_to_green == 1.0
    assert summary.served_by == ("lmstudio/m",)


def test_the_report_has_a_row_per_arm_and_a_paired_line() -> None:
    results = [
        _result(f"t{i}", arm, seed, green=arm == "fix" or i % 2 == 0)
        for i in range(6)
        for arm in ("single", "fix")
        for seed in (0, 1, 2)
    ]
    lines = format_report(results)
    assert lines[1].startswith("single") and lines[2].startswith("fix")
    assert lines[-1].startswith("fix vs single: +")


def test_an_unknown_arm_has_no_summary() -> None:
    with pytest.raises(BenchError, match="nope"):
        summarize([_result("gcd", "single", 0, green=True)], "nope")


def test_adapters_follow_the_dialect() -> None:
    assert isinstance(adapter_for(Dialect.NASM), NasmAdapter)
    assert isinstance(adapter_for(Dialect.GAS_ATT), GasAttAdapter)


def test_the_report_command_prints_the_table(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    for arm in ("single", "fix"):
        for task in ("a", "b", "c"):
            append_result(path, _result(task, arm, 0, green=arm == "fix"))
    outcome = CliRunner().invoke(app, ["bench", "report", str(path)])
    assert outcome.exit_code == 0, outcome.output
    assert "fix vs single" in outcome.output


def test_the_report_command_fails_on_a_missing_file(tmp_path: Path) -> None:
    outcome = CliRunner().invoke(app, ["bench", "report", str(tmp_path / "none.jsonl")])
    assert outcome.exit_code == 1


def test_the_run_command_rejects_an_unknown_arm() -> None:
    outcome = CliRunner().invoke(app, ["bench", "run", "--arm", "nope", "--bench-root", str(BENCH)])
    assert outcome.exit_code == 2


def test_the_run_command_rejects_an_unknown_model() -> None:
    outcome = CliRunner().invoke(app, ["bench", "run", "--model", "nope", "--bench-root", str(BENCH)])
    assert outcome.exit_code == 2
