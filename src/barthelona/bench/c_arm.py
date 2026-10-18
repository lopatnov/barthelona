"""The c-gcc arm: the model writes C, gcc compiles it to Intel-syntax GAS, the usual ladder judges the result.

D-040 workaround (a): a NASM task is verified as a GAS Intel module, so the task is re-targeted in code
rather than duplicated on disk. Nothing from the model runs on the host: gcc runs in `bart-tc` through the
executor session (invariant 2).
"""

from __future__ import annotations

import io
import re
import tarfile
import time
from pathlib import Path

from barthelona.bench.runner import Verifier
from barthelona.bench.task import BenchTask
from barthelona.domain.enums import DiagnosticLevel, Dialect, Level
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.executors import Command, ExecLimits, Executor
from barthelona.toolchains import parse_assembler_output

_GAS_INTEL_PRESET = "linux-x64-gas-intel"
_COMPILE_TIMEOUT = 20.0
_MAX_STDERR = 64 * 1024
_MAX_ASSEMBLY = 4 * 1024 * 1024
_MAX_MESSAGE_CHARS = 600
_GNU_STACK = ".note.GNU-stack"
_GNU_STACK_SECTION = '\t.section\t.note.GNU-stack,"",@progbits\n'
_COLUMN = re.compile(
    rb"^([^:\s][^:]*:\d+):\d+: ", re.MULTILINE
)  # gcc prints file:line:col:, the parser wants file:line:


def gcc_argv(source: str, output: str) -> tuple[str, ...]:
    """`gcc -O2 -S` flags that keep the output a plain Intel-syntax module (no CFI, no PIE, no CET)."""
    return (
        "gcc",
        "-O2",
        "-S",
        "-masm=intel",
        "-fno-asynchronous-unwind-tables",
        "-fno-pie",
        "-fcf-protection=none",
        "-o",
        output,
        source,
    )


def c_source_name(task: BenchTask) -> str:
    """The one file the model writes in the c-gcc arm."""
    return f"{task.module}.c"


def gas_intel_variant(task: BenchTask) -> BenchTask:
    """The same task re-targeted at GAS Intel, with every module path ending in `.s`."""
    symbols = {
        name: symbol.model_copy(update={"module": Path(symbol.module).with_suffix(".s").as_posix()})
        for name, symbol in task.registry.symbols.items()
    }
    target = task.registry.target.model_copy(
        update={"preset": _GAS_INTEL_PRESET, "dialect": Dialect.GAS_INTEL}
    )
    registry = task.registry.model_copy(update={"target": target, "symbols": symbols})
    return task.model_copy(update={"dialect": Dialect.GAS_INTEL, "registry": registry})


def with_gnu_stack(assembly: str) -> str:
    """*assembly* with a non-executable-stack note: gcc normally emits one, ld >= 2.39 warns without it."""
    if _GNU_STACK in assembly:
        return assembly
    return assembly.rstrip("\n") + "\n" + _GNU_STACK_SECTION


def _tar_of(path: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        archive.add(path, arcname=path.name)
    return buffer.getvalue()


def _compile_failure(path: Path, stderr: bytes, secs: float) -> LevelResult:
    """A failed V0 whose diagnostics are gcc's, so the fix prompt shows them like any oracle output."""
    diagnostics = [
        d.model_copy(update={"level": DiagnosticLevel.V0})
        for d in parse_assembler_output("gcc", _COLUMN.sub(rb"\1: ", stderr))
    ]
    if not any(d.severity == Severity.FATAL for d in diagnostics):
        message = stderr.decode("utf-8", errors="replace").strip() or "gcc exited non-zero"
        diagnostics.append(
            Diagnostic(
                tool="gcc",
                level=DiagnosticLevel.V0,
                severity=Severity.FATAL,
                message=message[:_MAX_MESSAGE_CHARS],
                file=path.name,
            )
        )
    return LevelResult(level=Level.V0, status="fail", diagnostics=diagnostics, secs=secs)


class CGccVerifier:
    """Compiles a model's `.c` in `bart-tc`, then runs the wrapped verifier on the `.s` as GAS Intel.

    Any other source goes to the wrapped verifier untouched, so one instance serves every arm.
    """

    def __init__(self, executor: Executor, ladder: Verifier) -> None:
        self._executor = executor
        self._ladder = ladder

    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]:
        (source,) = sources
        if source.suffix != ".c":
            return await self._ladder.verify(task, sources, run_id, attempt)
        started = time.monotonic()
        assembly = await self._compile(source, f"{run_id}-cc", attempt)
        if isinstance(assembly, LevelResult):
            return [assembly.model_copy(update={"secs": time.monotonic() - started})]
        target = source.with_suffix(".s")
        target.write_text(with_gnu_stack(assembly), encoding="utf-8", newline="\n")
        return await self._ladder.verify(gas_intel_variant(task), [target], run_id, attempt)

    async def _compile(self, source: Path, run_id: str, attempt: int) -> str | LevelResult:
        """The assembly text, or the failed `LevelResult` that carries gcc's diagnostics."""
        session = await self._executor.open_session(run_id, attempt)
        await session.stage(_tar_of(source))
        out = session.path(source.with_suffix(".s").name)
        limits = ExecLimits(timeout=_COMPILE_TIMEOUT, max_stderr_bytes=_MAX_STDERR)
        compiled = await session.run(Command(argv=gcc_argv(session.path(source.name), out)), limits)
        if compiled.returncode != 0:
            return _compile_failure(source, compiled.stderr, compiled.elapsed)
        shown = await session.run(Command(argv=("cat", out)), ExecLimits(max_stdout_bytes=_MAX_ASSEMBLY))
        return shown.stdout.decode("utf-8", errors="replace")
