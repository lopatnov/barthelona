"""V6 golden I/O against a FakeExecutor sandbox (no Docker)."""

from __future__ import annotations

from pathlib import Path

from barthelona.domain.enums import Level
from barthelona.domain.verification import Expectation, TestCase, TestKind, TestOrigin
from barthelona.executors._types import ExecResult
from barthelona.executors.fake import FakeExecutor
from barthelona.toolchains.nasm import NasmAdapter
from barthelona.verification.golden import run_v6
from barthelona.verification.ladder import dod_satisfied, run_ladder

_BINARY = "/fake/work/t/0/output.elf"


def _case(case_id: str = "t1", stdout: str | None = "ok\n", exit_code: int | None = None) -> TestCase:
    return TestCase(
        id=case_id,
        kind=TestKind.IO_GOLDEN,
        level=Level.V6,
        inputs={"stdin": "x"},
        expect=Expectation(stdout=stdout, exit_code=exit_code),
        origin=TestOrigin.USER,
    )


def _sandbox(stdout: bytes = b"ok\n", returncode: int = 0, stderr: bytes = b"") -> FakeExecutor:
    result = ExecResult(returncode=returncode, stdout=stdout, stderr=stderr, elapsed=0.0)
    return FakeExecutor(executor_id="sandbox", may_run_untrusted=True, responses={(_BINARY,): result})


async def test_matching_output_passes() -> None:
    session = await _sandbox().open_session("t", 0)
    result = await run_v6(session, [_case()])
    assert result.level == Level.V6
    assert result.status == "pass"


async def test_stdout_mismatch_is_fatal() -> None:
    session = await _sandbox(stdout=b"nope\n").open_session("t", 0)
    result = await run_v6(session, [_case()])
    assert result.status == "fail"
    assert "t1" in result.diagnostics[0].message
    assert "'nope\\n'" in result.diagnostics[0].message


async def test_nonzero_exit_fails_by_default() -> None:
    session = await _sandbox(returncode=137, stderr=b"Killed").open_session("t", 0)
    result = await run_v6(session, [_case()])
    assert result.status == "fail"
    assert "exit code 137" in result.diagnostics[0].message


async def test_expected_exit_code_is_honoured() -> None:
    session = await _sandbox(returncode=3).open_session("t", 0)
    assert (await run_v6(session, [_case(exit_code=3)])).status == "pass"


async def test_stdout_is_unchecked_when_not_specified() -> None:
    session = await _sandbox(stdout=b"anything").open_session("t", 0)
    assert (await run_v6(session, [_case(stdout=None)])).status == "pass"


async def test_one_diagnostic_per_failing_case() -> None:
    session = await _sandbox(stdout=b"bad").open_session("t", 0)
    result = await run_v6(session, [_case("a"), _case("b")])
    assert [d.message.split(":")[0] for d in result.diagnostics] == ["a", "b"]


def _source(tmp_path: Path) -> list[Path]:
    path = tmp_path / "hello.asm"
    path.write_text("; stub\n", encoding="utf-8")
    return [path]


async def test_ladder_reports_v6_unsupported_without_a_sandbox(tmp_path: Path) -> None:
    results = await run_ladder(
        Level.V6, FakeExecutor(), NasmAdapter(), _source(tmp_path), "t", tests=[_case()]
    )
    v6 = results[-1]
    assert (v6.level, v6.status) == (Level.V6, "unsupported")
    assert "sandbox" in v6.diagnostics[0].message


async def test_ladder_reports_v6_unsupported_without_golden_cases(tmp_path: Path) -> None:
    results = await run_ladder(
        Level.V6, FakeExecutor(), NasmAdapter(), _source(tmp_path), "t", sandbox=_sandbox()
    )
    assert results[-1].status == "unsupported"
    assert "io_golden" in results[-1].diagnostics[0].message


async def test_ladder_runs_v6_after_a_passing_link(tmp_path: Path) -> None:
    results = await run_ladder(
        Level.V6,
        FakeExecutor(),
        NasmAdapter(),
        _source(tmp_path),
        "t",
        sandbox=_sandbox(),
        tests=[_case()],
    )
    assert results[-1].status == "pass"
    assert dod_satisfied([Level.V0, Level.V1, Level.V2, Level.V6], results)
    assert not dod_satisfied([Level.V5, Level.V6], results)  # V5 has no check yet


def test_empty_requirement_is_never_satisfied() -> None:
    assert not dod_satisfied([], [])
