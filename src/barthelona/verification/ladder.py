"""Verification ladder runner (architecture §13, D-046).

The ladder is the central acceptance criterion: assembly oracles decide,
models propose (invariant 1).  This module walks the registered
:class:`~barthelona.verification.registry.LevelCheck` objects of a target
family in level order; the checks themselves live next to their family
(:mod:`barthelona.verification.native_asm`).

1. Open a session for the attempt and stage the source files into it.
2. For each level up to *up_to*, run the family's check.  A level the family
   has no check for, or whose check does not support the target, is recorded as
   ``unsupported`` with the reason; it is never skipped silently.
3. After a failed level, later levels are recorded as ``skipped``, except
   checks registered ``always_run``.
4. :func:`dod_satisfied` decides "done": every required level must be ``pass``.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Collection
from pathlib import Path
from typing import Literal

from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import DiagnosticLevel, Level, Linker, ObjFormat
from barthelona.domain.verification import Diagnostic, LevelResult, Severity, TestCase
from barthelona.executors.protocol import Executor
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification.native_asm import register_native_asm
from barthelona.verification.registry import NATIVE_ASM, CheckRegistry, LadderContext

_LEVELS = tuple(Level)


def default_registry() -> CheckRegistry:
    registry = CheckRegistry()
    register_native_asm(registry)
    return registry


def _make_tar(source_files: list[Path]) -> bytes:
    """Bundle *source_files* into a tar archive, each at the root level."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        for path in source_files:
            archive.add(path, arcname=path.name)
    return buf.getvalue()


def _non_pass(
    level: Level, status: Literal["skipped", "unsupported"], reason: str | None = None
) -> LevelResult:
    """A level that did not run; an unsupported one carries its reason as a note."""
    notes = (
        [
            Diagnostic(
                tool="ladder", level=DiagnosticLevel(level.value), severity=Severity.NOTE, message=reason
            )
        ]
        if reason
        else []
    )
    return LevelResult(level=level, status=status, diagnostics=notes, secs=0.0)


async def _run_level(
    registry: CheckRegistry,
    family: str,
    level: Level,
    ctx: LadderContext,
    failed: bool,
) -> LevelResult:
    check = registry.get(family, level)
    if check is None:
        return _non_pass(level, "unsupported", f"no {family} check registered for {level}")
    unsupported = check.supports(ctx)
    if unsupported is not None:
        return _non_pass(level, "unsupported", unsupported.reason)
    if failed and not check.always_run:
        return _non_pass(level, "skipped")
    return await check.run(ctx)


async def run_ladder(
    up_to: Level,
    executor: Executor,
    adapter: DialectAdapter,
    source_files: list[Path],
    run_id: str,
    attempt: int = 0,
    obj_format: ObjFormat = ObjFormat.ELF64,
    linker: Linker = Linker.LD,
    entry: str = "_start",
    family: str = NATIVE_ASM,
    contracts: ContractRegistry | None = None,
    sandbox: Executor | None = None,
    tests: list[TestCase] | None = None,
    checks: CheckRegistry | None = None,
) -> list[LevelResult]:
    """Run the ladder from V0 up to *up_to* and return one result per level.

    Parameters
    ----------
    up_to:
        Highest level to attempt.
    executor:
        Executor implementation; :class:`~barthelona.executors.fake.FakeExecutor`
        for tests, :class:`~barthelona.executors.agent.AgentExecutor` in production.
    adapter:
        Dialect adapter for the project's assembler.
    source_files:
        Ordered list of local source file paths to stage and assemble.
    run_id, attempt:
        Identify the session's work directory (D-043); parallel attempts never share one.
    obj_format, linker, entry:
        Target settings the checks read from the context.
    family:
        Target family whose checks are used (``native-asm``).
    contracts:
        Contract registry; when given, V1 also compares each object's ``nm`` symbols with it.
    sandbox:
        Executor for generated binaries (``bart-run``); V6 is unsupported without it.
    tests:
        Test cases; V6 runs the ``io_golden`` ones.
    checks:
        Check registry; the built-in one when omitted.
    """
    if not source_files:
        return []

    checks = checks or default_registry()
    session = await executor.open_session(run_id, attempt)
    await session.stage(_make_tar(source_files))
    ctx = LadderContext(
        session=session,
        adapter=adapter,
        source_files=source_files,
        obj_format=obj_format,
        linker=linker,
        entry=entry,
        contracts=contracts,
        sandbox=await sandbox.open_session(run_id, attempt) if sandbox is not None else None,
        tests=tests or [],
    )

    results: list[LevelResult] = []
    failed = False
    for level in levels_through(up_to):
        result = await _run_level(checks, family, level, ctx, failed)
        results.append(result)
        failed = failed or result.status == "fail"
    return results


def levels_through(up_to: Level) -> tuple[Level, ...]:
    """Every ladder level from V0 up to and including *up_to*."""
    return _LEVELS[: _LEVELS.index(up_to) + 1]


def dod_satisfied(required: Collection[Level], results: list[LevelResult]) -> bool:
    """Definition of Done: every *required* level has a ``pass`` result (D-046).

    ``unsupported`` and ``skipped`` are not passes: an oracle that cannot run does not accept work.
    An empty requirement is never satisfied. The caller names the required levels,
    so the MVP set (V0-V2, V5, V6) can omit the Phase 2 levels.
    """
    passed = {r.level for r in results if r.status == "pass"}
    return bool(required) and all(level in passed for level in required)
