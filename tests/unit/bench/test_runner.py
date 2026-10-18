"""The fix-loop runner with a scripted gateway and a scripted verifier (no model, no toolchain)."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.bench import Arm, BenchTask, RunSettings, TaskRun, load_prompts, load_suite, run_task
from barthelona.domain.enums import DiagnosticLevel, StopReason
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.llm import FakeGateway, GatewayError

BENCH = Path(__file__).resolve().parents[3] / "bench"
TASK = next(task for task in load_suite(BENCH, "dev") if task.id == "gcd")
GOOD = "=== FILE: gcd.asm ===\nret\n=== END ==="
OTHER_FILE = "=== FILE: evil.asm ===\nret\n=== END ==="


def _results(*statuses: str) -> list[LevelResult]:
    levels = ["V0", "V1", "V2", "V5"]
    results = []
    for level, status in zip(levels, statuses, strict=False):
        diagnostics = (
            [
                Diagnostic(
                    tool="harness", level=DiagnosticLevel.V5, severity=Severity.FATAL, message="gcd_0: got 3"
                )
            ]
            if status == "fail"
            else []
        )
        results.append(LevelResult(level=level, status=status, diagnostics=diagnostics, secs=0))  # type: ignore[arg-type]
    return results


class _Verifier:
    def __init__(self, *outcomes: list[LevelResult]) -> None:
        self.outcomes = list(outcomes)
        self.sources: list[list[Path]] = []

    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]:  # NOSONAR S7503
        self.sources.append(sources)
        return self.outcomes.pop(0)


def _run(tmp_path: Path, gateway: FakeGateway, verifier: _Verifier) -> TaskRun:
    return TaskRun(
        task=TASK,
        seed=3,
        gateway=gateway,
        verifier=verifier,
        prompts=load_prompts(BENCH),
        source_name="gcd.asm",
        work_root=tmp_path,
        settings=RunSettings(),
    )


PASS = _results("pass", "pass", "pass", "pass")
FAIL_V5 = _results("pass", "pass", "pass", "fail")


async def test_first_try_pass_is_green_and_first_try(tmp_path: Path) -> None:
    result = await run_task(_run(tmp_path, FakeGateway([GOOD]), _Verifier(PASS)), Arm("single", 0))
    assert (result.stop_reason, result.passed, result.first_try) == (StopReason.GREEN, True, True)
    assert result.attempts[0].levels == {"V0": "pass", "V1": "pass", "V2": "pass", "V5": "pass"}


async def test_the_model_file_is_written_where_the_ladder_will_read_it(tmp_path: Path) -> None:
    verifier = _Verifier(PASS)
    await run_task(_run(tmp_path, FakeGateway([GOOD]), verifier), Arm("single", 0))
    (path,) = verifier.sources[0]
    assert path.name == "gcd.asm"
    assert path.read_text(encoding="utf-8") == "ret\n"


async def test_the_single_arm_stops_after_one_failed_attempt(tmp_path: Path) -> None:
    gateway = FakeGateway([GOOD, GOOD])
    result = await run_task(_run(tmp_path, gateway, _Verifier(FAIL_V5)), Arm("single", 0))
    assert (result.stop_reason, len(result.attempts), len(gateway.calls)) == (StopReason.MAX_ATTEMPTS, 1, 1)


async def test_the_fix_arm_feeds_oracle_output_back_and_can_recover(tmp_path: Path) -> None:
    gateway = FakeGateway([GOOD, GOOD])
    result = await run_task(_run(tmp_path, gateway, _Verifier(FAIL_V5, PASS)), Arm("fix", 2))
    assert (result.stop_reason, result.first_try, len(result.attempts)) == (StopReason.GREEN, False, 2)
    second = gateway.calls[1][1].messages
    assert [m.role for m in second] == ["user", "assistant", "user"]
    assert "V5: fail" in second[2].content
    assert "gcd_0: got 3" in second[2].content
    assert gateway.calls[0][1].seed == 3


async def test_an_envelope_error_is_an_attempt_and_is_fed_back(tmp_path: Path) -> None:
    gateway = FakeGateway(["no envelope here", GOOD])
    result = await run_task(_run(tmp_path, gateway, _Verifier(PASS)), Arm("fix", 1))
    assert result.attempts[0].envelope_errors
    assert result.attempts[0].levels == {}
    assert "was not accepted" in gateway.calls[1][1].messages[2].content
    assert result.passed


async def test_a_file_outside_the_write_scope_never_reaches_the_ladder(tmp_path: Path) -> None:
    verifier = _Verifier()
    result = await run_task(_run(tmp_path, FakeGateway([OTHER_FILE]), verifier), Arm("single", 0))
    assert verifier.sources == []
    assert "outside the write scope" in result.attempts[0].envelope_errors[0]


async def test_attempts_are_bounded_by_the_arm(tmp_path: Path) -> None:
    gateway = FakeGateway([GOOD] * 5)
    result = await run_task(_run(tmp_path, gateway, _Verifier(*[FAIL_V5] * 5)), Arm("fix", 2))
    assert (result.stop_reason, len(result.attempts)) == (StopReason.MAX_ATTEMPTS, 3)


async def test_the_token_budget_stops_the_loop(tmp_path: Path) -> None:
    long_reply = GOOD + " word" * 50
    result = await run_task(
        _run(tmp_path, FakeGateway([long_reply] * 3), _Verifier(*[FAIL_V5] * 3)),
        Arm("fix", 5, max_total_tokens=40),
    )
    assert (result.stop_reason, len(result.attempts)) == (StopReason.BUDGET_TOKENS, 1)


async def test_a_gateway_failure_is_a_stop_reason_not_a_crash(tmp_path: Path) -> None:
    result = await run_task(_run(tmp_path, FakeGateway([GatewayError("down")]), _Verifier()), Arm("fix", 2))
    assert (result.stop_reason, result.attempts) == (StopReason.NO_MODEL_AVAILABLE, ())


@pytest.mark.parametrize(
    "statuses", [("pass", "pass", "pass", "unsupported"), ("pass", "pass", "pass", "skipped")]
)
async def test_an_oracle_that_cannot_run_is_not_a_pass(tmp_path: Path, statuses: tuple[str, ...]) -> None:
    result = await run_task(
        _run(tmp_path, FakeGateway([GOOD]), _Verifier(_results(*statuses))), Arm("single", 0)
    )
    assert not result.passed
