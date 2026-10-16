"""Verification ladder V0–V2 runner (architecture §13, Phase 0).

The ladder is the central acceptance criterion: assembly oracles decide,
models propose (invariant 1).  This module implements the deterministic
levels V0 (syntax), V1 (assemble), and V2 (link).

V3 (static ABI lint) and V4 (Unicorn emulator checks) are Phase 2.
V5 (C-harness tests) and V6 (golden I/O) are Phase 0 deliverables but
require the sandbox executor (``bart-run``), which ships after the
toolchain images are built.

Architecture
------------
1. Stage source files to the executor's work directory via
   :meth:`~barthelona.executors.protocol.Executor.stage`.
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
from pathlib import Path, PurePosixPath

from barthelona.domain.enums import DiagnosticLevel, Level, Linker, ObjFormat
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.executors._types import Command, ExecLimits
from barthelona.executors.protocol import Executor
from barthelona.toolchains.dialect import DialectAdapter

_TC_CONTAINER = "bart-tc"
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


def _docker_exec(container: str, argv: tuple[str, ...]) -> tuple[str, ...]:
    return ("docker", "exec", container, *argv)


def _work_path(work_dir: str, name: str) -> str:
    return str(PurePosixPath(work_dir) / name)


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


def _make_link_error(stderr: bytes, level: DiagnosticLevel = DiagnosticLevel.V2) -> Diagnostic:
    message = stderr.decode("utf-8", errors="replace").strip() or "linker exited non-zero"
    return Diagnostic(
        tool="ld",
        level=level,
        severity=Severity.FATAL,
        message=message,
    )


def run_v0(
    executor: Executor,
    adapter: DialectAdapter,
    source_files: list[Path],
    work_dir: str,
    container: str = _TC_CONTAINER,
    timeout: float = 10.0,
) -> LevelResult:
    """V0: syntax-only check for every source file (no output produced)."""
    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []
    lim = ExecLimits(timeout=timeout, max_stderr_bytes=64 * 1024)

    for path in source_files:
        staged = _work_path(work_dir, path.name)
        argv = _docker_exec(container, adapter.syntax_check_argv(staged))
        result = executor.run(Command(argv=argv), lim)
        if result.returncode != 0:
            diagnostics.append(
                _make_error_diagnostic(result.stderr, path.name, DiagnosticLevel.V0)
            )
        else:
            diagnostics.extend(
                _set_level(d, DiagnosticLevel.V0)
                for d in adapter.parse_diagnostics(result.stdout, result.stderr, path.name)
            )

    status = "pass" if not any(d.severity == Severity.FATAL for d in diagnostics) else "fail"
    return LevelResult(
        level=Level.V0,
        status=status,
        diagnostics=diagnostics,
        secs=time.monotonic() - t0,
    )


def run_v1(
    executor: Executor,
    adapter: DialectAdapter,
    source_files: list[Path],
    work_dir: str,
    obj_format: ObjFormat = ObjFormat.ELF64,
    container: str = _TC_CONTAINER,
    timeout: float = 15.0,
) -> tuple[LevelResult, list[str]]:
    """V1: assemble each source file; return the result and a list of object paths.

    Phase 0 note: the ``nm``/registry symbol check (architecture §13.1 — exports
    exact, undefined ⊆ imports ∪ allow-list) is deferred until ``contracts.yaml``
    is populated.  This level currently only assembles.
    """
    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []
    object_paths: list[str] = []
    lim = ExecLimits(timeout=timeout, max_stderr_bytes=64 * 1024)

    for path in source_files:
        staged_src = _work_path(work_dir, path.name)
        obj_name = Path(path.name).stem + ".o"
        staged_obj = _work_path(work_dir, obj_name)

        argv = _docker_exec(
            container,
            adapter.assemble_argv(staged_src, staged_obj, obj_format),
        )
        result = executor.run(Command(argv=argv), lim)
        if result.returncode != 0:
            diagnostics.append(
                _make_error_diagnostic(result.stderr, path.name, DiagnosticLevel.V1)
            )
        else:
            object_paths.append(staged_obj)
            diagnostics.extend(
                _set_level(d, DiagnosticLevel.V1)
                for d in adapter.parse_diagnostics(result.stdout, result.stderr, path.name)
            )

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


def run_v2(
    executor: Executor,
    object_paths: list[str],
    work_dir: str,
    linker: Linker = Linker.LD,
    entry: str = "_start",
    container: str = _TC_CONTAINER,
    timeout: float = 15.0,
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
    output = _work_path(work_dir, "output.elf")
    argv = _docker_exec(
        container,
        (linker_tool, "-e", entry, "-o", output, *object_paths),
    )
    lim = ExecLimits(timeout=timeout, max_stderr_bytes=64 * 1024)
    result = executor.run(Command(argv=argv), lim)

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


def run_ladder(
    up_to: Level,
    executor: Executor,
    adapter: DialectAdapter,
    source_files: list[Path],
    work_dir: str,
    obj_format: ObjFormat = ObjFormat.ELF64,
    linker: Linker = Linker.LD,
    entry: str = "_start",
    container: str = _TC_CONTAINER,
) -> list[LevelResult]:
    """Run the ladder from V0 up to *up_to* and return one result per level.

    Files are staged to *work_dir* before the first level runs.  If a level
    fails, higher levels are recorded as ``skipped``.

    Parameters
    ----------
    up_to:
        Highest level to attempt (V0, V1, or V2 in Phase 0).
    executor:
        Executor implementation; :class:`~barthelona.executors.fake.FakeExecutor`
        for tests, :class:`~barthelona.executors.wsl.WslExecutor` in production.
    adapter:
        Dialect adapter for the project's assembler.
    source_files:
        Ordered list of local source file paths to stage and assemble.
    work_dir:
        Absolute WSL path where files are staged (e.g.
        ``~/.cache/barthelona/verify-tmp``).
    obj_format:
        Object file format for the assembler and linker.
    linker:
        Linker binary to use for V2.
    entry:
        Entry-point symbol for the linker (default ``_start``).
    container:
        Docker container name (``bart-tc``).
    """
    if not source_files:
        return []

    executor.stage(_make_tar(source_files))

    levels_to_run = [lvl for lvl in _LEVEL_ORDER if _level_index(lvl) <= _level_index(up_to)]
    results: list[LevelResult] = []
    object_paths: list[str] = []
    failed = False

    for level in levels_to_run:
        if failed:
            results.append(LevelResult(level=level, status="skipped", diagnostics=[], secs=0.0))
            continue

        if level == Level.V0:
            r = run_v0(executor, adapter, source_files, work_dir, container)
            results.append(r)
            failed = r.status == "fail"

        elif level == Level.V1:
            r, object_paths = run_v1(executor, adapter, source_files, work_dir, obj_format, container)
            results.append(r)
            failed = r.status == "fail"

        elif level == Level.V2:
            r = run_v2(executor, object_paths, work_dir, linker, entry, container)
            results.append(r)
            failed = r.status == "fail"

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _level_index(level: Level) -> int:
    order = {Level.V0: 0, Level.V1: 1, Level.V2: 2, Level.V3: 3,
             Level.V4: 4, Level.V5: 5, Level.V6: 6, Level.V7: 7, Level.V8: 8}
    return order.get(level, 99)


def _set_level(diagnostic: Diagnostic, level: DiagnosticLevel) -> Diagnostic:
    return diagnostic.model_copy(update={"level": level})
