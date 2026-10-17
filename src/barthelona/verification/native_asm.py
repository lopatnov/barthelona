"""V0-V2 checks for native assembly targets (architecture §13.1, family ``native-asm``).

V3 (static ABI lint) and V4 (Unicorn) are Phase 2; V5 (C harness) and V6 (golden
I/O) need the ``bart-run`` sandbox executor (issue #47).  They register here
when they land.
"""

from __future__ import annotations

import time
from pathlib import Path

from barthelona.contracts import check_object_symbols, parse_nm
from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import DiagnosticLevel, Level, Linker, ObjFormat
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.executors._types import Command, ExecLimits, ExecResult
from barthelona.executors.protocol import Session
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification.registry import NATIVE_ASM, CheckRegistry, LadderContext, Unsupported

_LINKER_CMD: dict[Linker, str] = {
    Linker.LD: "ld",
    Linker.LIBC: "gcc",
}


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


def _set_level(diagnostic: Diagnostic, level: DiagnosticLevel) -> Diagnostic:
    return diagnostic.model_copy(update={"level": level})


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


async def _symbol_diagnostics(
    session: Session,
    contracts: ContractRegistry,
    source: str,
    staged_obj: str,
    limits: ExecLimits,
) -> list[Diagnostic]:
    """Compare one object's ``nm`` symbols with the registry; a failing ``nm`` is fatal."""
    result = await session.run(Command(argv=("nm", "-P", "-g", staged_obj)), limits)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip() or "nm exited non-zero"
        return [
            Diagnostic(
                tool="nm", level=DiagnosticLevel.V1, severity=Severity.FATAL, message=message, file=source
            )
        ]
    return check_object_symbols(contracts, source, parse_nm(result.stdout))


async def run_v1(
    session: Session,
    adapter: DialectAdapter,
    source_files: list[Path],
    obj_format: ObjFormat = ObjFormat.ELF64,
    command_timeout: float = 15.0,
    contracts: ContractRegistry | None = None,
) -> tuple[LevelResult, list[str]]:
    """V1: assemble each source file; return the result and a list of object paths.

    With a contract registry, every object that assembled is also checked with
    ``nm`` (architecture §13.1): exports exact, undefined symbols a subset of
    the declared imports plus the allow-list.
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
        if contracts is not None and result.returncode == 0:
            diagnostics.extend(await _symbol_diagnostics(session, contracts, path.name, staged_obj, lim))

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


class SyntaxCheck:
    """V0 as a registered check."""

    level = Level.V0
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:  # NOSONAR S1172: Protocol signature
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        return await run_v0(ctx.session, ctx.adapter, ctx.source_files)


class AssembleCheck:
    """V1 as a registered check; leaves the object paths on the context for V2."""

    level = Level.V1
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:  # NOSONAR S1172: Protocol signature
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        result, ctx.object_paths = await run_v1(
            ctx.session, ctx.adapter, ctx.source_files, ctx.obj_format, contracts=ctx.contracts
        )
        return result


class LinkCheck:
    """V2 as a registered check."""

    level = Level.V2
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:  # NOSONAR S1172: Protocol signature
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        return await run_v2(ctx.session, ctx.object_paths, ctx.linker, ctx.entry)


def register_native_asm(registry: CheckRegistry) -> None:
    """Register V0-V2 for the ``native-asm`` family."""
    for check in (SyntaxCheck(), AssembleCheck(), LinkCheck()):
        registry.register(NATIVE_ASM, check)
