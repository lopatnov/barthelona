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
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from barthelona.contracts.codegen import render_all
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


def _make_tar(source_files: list[Path], generated: Mapping[str, str]) -> bytes:
    """Bundle *source_files* (each at the root level) and the generated files (at their ``gen/`` paths)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        for path in source_files:
            archive.add(path, arcname=path.name)
        for name, text in sorted(generated.items()):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
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


@dataclass
class LadderOptions:
    """The optional inputs of :func:`run_ladder`; the defaults describe a plain NASM/ELF64 build."""

    obj_format: ObjFormat = ObjFormat.ELF64
    linker: Linker = Linker.LD
    entry: str = "_start"
    family: str = NATIVE_ASM
    contracts: ContractRegistry | None = (
        None  # V1 compares nm symbols with it; V5 generates harnesses from it
    )
    sandbox: Executor | None = None  # bart-run; V5 and V6 are unsupported without it
    tests: list[TestCase] = field(default_factory=list)  # V5 runs c_harness cases, V6 the io_golden ones
    checks: CheckRegistry | None = None  # the built-in registry when omitted


async def run_ladder(
    up_to: Level,
    executor: Executor,
    adapter: DialectAdapter,
    source_files: list[Path],
    run_id: str,
    attempt: int = 0,
    options: LadderOptions | None = None,
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
    options:
        Target settings, contracts, tests, sandbox and check registry (see :class:`LadderOptions`).
        With contracts, the generated ``gen/`` files are staged next to the sources.
    """
    if not source_files:
        return []

    opts = options or LadderOptions()
    checks = opts.checks or default_registry()
    session = await executor.open_session(run_id, attempt)
    generated = render_all(opts.contracts, opts.tests) if opts.contracts is not None else {}
    await session.stage(_make_tar(source_files, generated))
    ctx = LadderContext(
        session=session,
        adapter=adapter,
        source_files=source_files,
        obj_format=opts.obj_format,
        linker=opts.linker,
        entry=opts.entry,
        contracts=opts.contracts,
        sandbox=await opts.sandbox.open_session(run_id, attempt) if opts.sandbox is not None else None,
        tests=opts.tests,
    )

    results: list[LevelResult] = []
    failed = False
    for level in levels_through(up_to):
        result = await _run_level(checks, opts.family, level, ctx, failed)
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
