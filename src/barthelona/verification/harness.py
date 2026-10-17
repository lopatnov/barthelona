"""V5: C-harness tests (architecture §13.1, §13.4).

Each ``c_harness`` case has a generated ``gen/harness/<id>.c`` that calls the tested
function.  gcc builds it together with the project's objects in the toolchain
container; the binary then runs in the ``bart-run`` sandbox (invariant 2).  The
module that defines the entry point is left out, because the harness has its own ``main``.
"""

from __future__ import annotations

import time
from pathlib import Path

from barthelona.contracts.cgen import c_harness_cases
from barthelona.contracts.symbols import module_stem
from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import DiagnosticLevel, Level
from barthelona.domain.verification import Diagnostic, LevelResult, Severity, TestCase
from barthelona.executors._types import Command, ExecLimits
from barthelona.executors.protocol import Session
from barthelona.verification.registry import LadderContext, Unsupported

_GCC_FLAGS = ("-Wall", "-Werror", "-no-pie", "-Wl,-z,noexecstack")


def _fatal(case: TestCase, code: str, message: str) -> Diagnostic:
    return Diagnostic(
        tool="harness",
        level=DiagnosticLevel.V5,
        severity=Severity.FATAL,
        code=code,
        message=f"{case.id}: {message}",
        symbol=case.symbol,
    )


def harness_objects(registry: ContractRegistry, object_paths: list[str], entry: str) -> list[str]:
    """The project's objects without the module that defines *entry*."""
    symbol = registry.symbols.get(entry)
    skipped = module_stem(symbol.module) if symbol is not None else None
    return [path for path in object_paths if Path(path).stem != skipped]


async def _build(session: Session, case: TestCase, objects: list[str], lim: ExecLimits) -> Diagnostic | None:
    binary = session.path(f"harness_{case.id}")
    source = session.path(f"gen/harness/{case.id}.c")
    result = await session.run(Command(argv=("gcc", *_GCC_FLAGS, "-o", binary, source, *objects)), lim)
    if result.returncode == 0:
        return None
    return _fatal(case, "harness.build", result.stderr.decode("utf-8", errors="replace").strip()[:500])


async def _run(sandbox: Session, case: TestCase, lim: ExecLimits) -> Diagnostic | None:
    result = await sandbox.run(Command(argv=(sandbox.path(f"harness_{case.id}"),)), lim)
    if result.returncode == 0:
        return None
    output = (result.stdout or result.stderr).decode("utf-8", errors="replace").strip()
    return _fatal(case, "harness.failed", output[:500] or f"exit code {result.returncode}")


async def run_v5(
    session: Session,
    sandbox: Session,
    cases: list[TestCase],
    objects: list[str],
    command_timeout: float = 20.0,
) -> LevelResult:
    """V5: build and run each C harness; one fatal diagnostic per failing case."""
    t0 = time.monotonic()
    lim = ExecLimits(timeout=command_timeout, max_stderr_bytes=64 * 1024)
    diagnostics: list[Diagnostic] = []
    for case in cases:
        failure = await _build(session, case, objects, lim) or await _run(sandbox, case, lim)
        if failure is not None:
            diagnostics.append(failure)
    status = "fail" if diagnostics else "pass"
    return LevelResult(level=Level.V5, status=status, diagnostics=diagnostics, secs=time.monotonic() - t0)


class HarnessCheck:
    """V5 as a registered check; needs contracts, a sandbox and at least one c_harness case."""

    level = Level.V5
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        if ctx.contracts is None:
            return Unsupported("no contract registry was provided, so no harness can be generated")
        if ctx.sandbox is None:
            return Unsupported("no sandbox executor (bart-run) was provided")
        if not c_harness_cases(ctx.tests):
            return Unsupported("no c_harness test cases for V5 were provided")
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        if ctx.contracts is None or ctx.sandbox is None:
            raise RuntimeError("V5 ran without contracts or a sandbox; supports() should have refused it")
        objects = harness_objects(ctx.contracts, ctx.object_paths, ctx.entry)
        return await run_v5(ctx.session, ctx.sandbox, c_harness_cases(ctx.tests), objects)
