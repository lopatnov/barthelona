"""Verification ladder V0-V2 runner (architecture §13, Phase 0).

The ladder is the central acceptance criterion: assembly oracles decide,
models propose (invariant 1).  This module implements the deterministic
levels V0 (syntax), V1 (assemble), and V2 (link).

V3 (static ABI lint) and V4 (Unicorn emulator checks) are Phase 2.
V5 (C-harness tests) and V6 (golden I/O) are Phase 0 deliverables but
require the sandbox executor (``bart-run``), which ships after the
toolchain images are built.

Architecture
------------
1. Open a session for the attempt and stage the source files into its work
   directory (:class:`~barthelona.executors.protocol.Session`).
2. For V0 and V1, run the per-dialect assembler command on each source file.
3. For V2, run the linker on all assembled object files.
4. Return a :class:`~barthelona.domain.verification.LevelResult` per level.

The caller (``barthelona verify``, or a future ``ladder`` node) picks
which levels to run by setting *up_to*.
"""

from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

from barthelona.domain.enums import DiagnosticLevel, Level, Linker, ObjFormat
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.executors._types import Command, ExecLimits, ExecResult
from barthelona.executors.protocol import Executor, Session
from barthelona.toolchains.dialect import DialectAdapter

_LEVEL_ORDER = [Level.V0, Level.V1, Level.V2]

_LINKER_CMD: dict[Linker, str] = {
    Linker.LD: "ld",
    Linker.LIBC: "gcc",
}


def _make_tar(source_files: list[Path]) -> bytes:
    """Bundle *source_files* into a tar archive, each at the root level."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        for path in source_files:
            archive.add(path, arcname=path.name)
    return buf.getvalue()


def _make_error_diagnostic(
    stderr: bytes,
    source: str,
    level: DiagnosticLevel,
) -> Diagnostic:
    message = stderr.decode("utf-8", errors="replace").strip() or "assembler exited non-zero"
    return Diagnostic(
        tool="assembler",
        level=level,
        severity=Severity.FATAL,
        message=message,
        file=Path(source).name,
    )


def _assembler_diagnostics(
    adapter: DialectAdapter,
    result: ExecResult,
    source: str,
    level: DiagnosticLevel,
) -> list[Diagnostic]:
    """Parsed diagnostics for one assembler run; a failed run always yields a fatal one."""
    parsed = [_set_level(d, level) for d in adapter.parse_diagnostics(result.stdout, result.stderr, source)]
    if result.returncode != 0 and not any(d.severity == Severity.FATAL for d in parsed):
        parsed.append(_make_error_diagnostic(result.stderr, source, level))
    return parsed


def _make_link_error(stderr: bytes, level: DiagnosticLevel = DiagnosticLevel.V2) -> Diagnostic:
    message = stderr.decode("utf-8", errors="replace").strip() or "linker exited non-zero"
    return Diagnostic(
        tool="ld",
        level=level,
        severity=Severity.FATAL,
        message=message,
    )


async def run_v0(
    session: Session,
    adapter: DialectAdapter,
    source_files: list[Path],
    command_timeout: float = 10.0,
) -> LevelResult:
    """V0: syntax-only check for every source file (no output produced)."""
    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []
    lim = ExecLimits(timeout=command_timeout, max_stderr_bytes=64 * 1024)

    for path in source_files:
        argv = adapter.syntax_check_argv(session.path(path.name))
        result = await session.run(Command(argv=argv), lim)
        diagnostics.extend(_assembler_diagnostics(adapter, result, path.name, DiagnosticLevel.V0))

    status = "pass" if not any(d.severity == Severity.FATAL for d in diagnostics) else "fail"
    return LevelResult(
        level=Level.V0,
        status=status,
        diagnostics=diagnostics,
        secs=time.monotonic() - t0,
    )


async def run_v1(
    session: Session,
    adapter: DialectAdapter,
    source_files: list[Path],
    obj_format: ObjFormat = ObjFormat.ELF64,
    command_timeout: float = 15.0,
) -> tuple[LevelResult, list[str]]:
    """V1: assemble each source file; return the result and a list of object paths.

    Phase 0 note: the ``nm``/registry symbol check (architecture §13.1 — exports
    exact, undefined is a subset of imports union allow-list) is deferred until ``contracts.yaml``
    is populated.  This level currently only assembles.
    """
    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []
    object_paths: list[str] = []
    lim = ExecLimits(timeout=command_timeout, max_stderr_bytes=64 * 1024)

    for path in source_files:
        staged_obj = session.path(Path(path.name).stem + ".o")
        argv = adapter.assemble_argv(session.path(path.name), staged_obj, obj_format)
        result = await session.run(Command(argv=argv), lim)
        if result.returncode == 0:
            object_paths.append(staged_obj)
        diagnostics.extend(_assembler_diagnostics(adapter, result, path.name, DiagnosticLevel.V1))

    status = "pass" if not any(d.severity == Severity.FATAL for d in diagnostics) else "fail"
    return (
        LevelResult(
            level=Level.V1,
            status=status,
            diagnostics=diagnostics,
            secs=time.monotonic() - t0,
        ),
        object_paths,
    )


async def run_v2(
    session: Session,
    object_paths: list[str],
    linker: Linker = Linker.LD,
    entry: str = "_start",
    command_timeout: float = 15.0,
) -> LevelResult:
    """V2: link all object files into an executable."""
    t0 = time.monotonic()
    if not object_paths:
        return LevelResult(
            level=Level.V2,
            status="skipped",
            diagnostics=[],
            secs=time.monotonic() - t0,
        )

    linker_tool = _LINKER_CMD.get(linker, "ld")
    argv = (linker_tool, "-e", entry, "-o", session.path("output.elf"), *object_paths)
    lim = ExecLimits(timeout=command_timeout, max_stderr_bytes=64 * 1024)
    result = await session.run(Command(argv=argv), lim)

    diagnostics: list[Diagnostic] = []
    if result.returncode != 0:
        diagnostics.append(_make_link_error(result.stderr))

    status = "pass" if not diagnostics else "fail"
    return LevelResult(
        level=Level.V2,
        status=status,
        diagnostics=diagnostics,
        secs=time.monotonic() - t0,
    )


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
) -> list[LevelResult]:
    """Run the ladder from V0 up to *up_to* and return one result per level.

    A session for (*run_id*, *attempt*) is opened and the sources are staged
    into it before the first level runs.  If a level fails, higher levels are
    recorded as ``skipped``.

    Parameters
    ----------
    up_to:
        Highest level to attempt (V0, V1, or V2 in Phase 0).
    executor:
        Executor implementation; :class:`~barthelona.executors.fake.FakeExecutor`
        for tests, :class:`~barthelona.executors.agent.AgentExecutor` in production.
    adapter:
        Dialect adapter for the project's assembler.
    source_files:
        Ordered list of local source file paths to stage and assemble.
    run_id, attempt:
        Identify the session's work directory (D-043); parallel attempts never share one.
    obj_format:
        Object file format for the assembler and linker.
    linker:
        Linker binary to use for V2.
    entry:
        Entry-point symbol for the linker (default ``_start``).
    """
    if not source_files:
        return []

    session = await executor.open_session(run_id, attempt)
    await session.stage(_make_tar(source_files))

    levels_to_run = [lvl for lvl in _LEVEL_ORDER if _level_index(lvl) <= _level_index(up_to)]
    results: list[LevelResult] = []
    object_paths: list[str] = []
    failed = False

    for level in levels_to_run:
        if failed:
            results.append(LevelResult(level=level, status="skipped", diagnostics=[], secs=0.0))
            continue

        if level == Level.V0:
            r = await run_v0(session, adapter, source_files)
            results.append(r)
            failed = r.status == "fail"

        elif level == Level.V1:
            r, object_paths = await run_v1(session, adapter, source_files, obj_format)
            results.append(r)
            failed = r.status == "fail"

        elif level == Level.V2:
            r = await run_v2(session, object_paths, linker, entry)
            results.append(r)
            failed = r.status == "fail"

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _level_index(level: Level) -> int:
    order = {
        Level.V0: 0,
        Level.V1: 1,
        Level.V2: 2,
        Level.V3: 3,
        Level.V4: 4,
        Level.V5: 5,
        Level.V6: 6,
        Level.V7: 7,
        Level.V8: 8,
    }
    return order.get(level, 99)


def _set_level(diagnostic: Diagnostic, level: DiagnosticLevel) -> Diagnostic:
    return diagnostic.model_copy(update={"level": level})
