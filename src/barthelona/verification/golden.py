"""V6: whole-program golden I/O in the ``bart-run`` sandbox (architecture §13.1, §13.4).

The linked program is run once per ``io_golden`` test case with the case's stdin;
stdout and the exit code are compared with the expectation.  The program runs
only through the sandbox executor (invariant 2).
"""

from __future__ import annotations

import time

from barthelona.domain.enums import DiagnosticLevel, Level
from barthelona.domain.verification import Diagnostic, LevelResult, Severity, TestCase, TestKind
from barthelona.executors._types import Command, ExecLimits, ExecResult
from barthelona.executors.protocol import Session
from barthelona.verification.registry import LadderContext, Unsupported

BINARY = "output.elf"  # written by V2 into the attempt's work directory
_SNIPPET = 80


def golden_cases(tests: list[TestCase]) -> list[TestCase]:
    return [t for t in tests if t.kind == TestKind.IO_GOLDEN and t.level == Level.V6]


def _stdin_of(case: TestCase) -> bytes | None:
    value = case.inputs.get("stdin")
    return value.encode("utf-8") if isinstance(value, str) else None


def _snippet(data: bytes | str) -> str:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    return repr(text if len(text) <= _SNIPPET else text[:_SNIPPET] + "...")


def _mismatch(case: TestCase, message: str) -> Diagnostic:
    return Diagnostic(
        tool="golden",
        level=DiagnosticLevel.V6,
        severity=Severity.FATAL,
        code="golden.mismatch",
        message=f"{case.id}: {message}",
        symbol=None,
    )


def _compare(case: TestCase, result: ExecResult) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    want_exit = case.expect.exit_code if case.expect.exit_code is not None else 0
    if result.returncode != want_exit:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        suffix = f" ({detail})" if detail else ""
        diagnostics.append(_mismatch(case, f"exit code {result.returncode}, expected {want_exit}{suffix}"))
    want_stdout = case.expect.stdout
    if want_stdout is not None and result.stdout.decode("utf-8", errors="replace") != want_stdout:
        diagnostics.append(
            _mismatch(case, f"stdout {_snippet(result.stdout)}, expected {_snippet(want_stdout)}")
        )
    return diagnostics


async def run_v6(
    sandbox: Session,
    cases: list[TestCase],
    command_timeout: float = 10.0,
) -> LevelResult:
    """V6: run the linked program against each golden case and compare its output."""
    t0 = time.monotonic()
    lim = ExecLimits(timeout=command_timeout, max_stderr_bytes=4 * 1024)
    diagnostics: list[Diagnostic] = []
    for case in cases:
        command = Command(argv=(sandbox.path(BINARY),), stdin=_stdin_of(case))
        diagnostics.extend(_compare(case, await sandbox.run(command, lim)))
    status = "fail" if diagnostics else "pass"
    return LevelResult(level=Level.V6, status=status, diagnostics=diagnostics, secs=time.monotonic() - t0)


class GoldenIoCheck:
    """V6 as a registered check; unsupported without a sandbox executor or golden cases."""

    level = Level.V6
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        if ctx.sandbox is None:
            return Unsupported("no sandbox executor (bart-run) was provided")
        if not golden_cases(ctx.tests):
            return Unsupported("no io_golden test cases for V6 were provided")
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        if ctx.sandbox is None:
            raise RuntimeError("V6 ran without a sandbox session; supports() should have refused it")
        return await run_v6(ctx.sandbox, golden_cases(ctx.tests))
