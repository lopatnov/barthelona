"""Assemble model-written NASM source on the host: the oracle that decides a ``chunked run`` result.

The source is only assembled (``nasm -f elf64``), never linked or run (invariant 2). Directives that make
the assembler read host files are refused first, because the text comes from a model. This is a stopgap for
runs outside the ladder; the real path is the sandboxed V0-V2 levels (roadmap follow-up on #206).
"""

from __future__ import annotations

import re
import shutil
import subprocess  # argv list only, never a shell (invariant 9)
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from barthelona.domain.verification import Severity
from barthelona.toolchains._diagnostics import parse_assembler_output

AssembleStatus = Literal["pass", "fail", "unavailable"]
_TIMEOUT_S = 20
_MAX_ERRORS = 12
_HOST_FILE_DIRECTIVE = re.compile(r"%\s*(include|pathsearch|depend)\b|\bincbin\b", re.IGNORECASE)

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


@dataclass(frozen=True)
class AssembleResult:
    status: AssembleStatus
    errors: tuple[str, ...] = ()


def _fail(message: str) -> AssembleResult:
    return AssembleResult("fail", (message,))


def assemble_source(source: str, nasm: str | None = None, runner: Runner = subprocess.run) -> AssembleResult:
    """``pass`` when NASM accepts *source*, ``fail`` with its errors, ``unavailable`` when it cannot run."""
    binary = nasm or shutil.which("nasm")
    if binary is None:
        return AssembleResult("unavailable", ("nasm was not found on PATH; pass --nasm <path>",))
    if not source.strip():
        return _fail("the source is empty")
    if _HOST_FILE_DIRECTIVE.search(source):
        return _fail("%include, %pathsearch, %depend and incbin are refused: they read files from the host")
    with tempfile.TemporaryDirectory(prefix="barthelona-asm-") as work:
        path = Path(work) / "main.asm"
        path.write_text(source + "\n", encoding="utf-8", newline="\n")
        try:
            done = runner(
                [binary, "-f", "elf64", "-o", str(Path(work) / "main.o"), str(path)],
                capture_output=True,
                timeout=_TIMEOUT_S,
                check=False,
                cwd=work,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AssembleResult("unavailable", (f"nasm did not run: {exc}",))
    if done.returncode == 0:
        return AssembleResult("pass")
    found = [d for d in parse_assembler_output("nasm", done.stderr) if d.severity is Severity.FATAL]
    errors = tuple(f"line {d.line}: {d.message}" if d.line else d.message for d in found[:_MAX_ERRORS])
    return AssembleResult(
        "fail", errors or (done.stderr.decode("utf-8", "replace").strip()[:500] or "nasm failed",)
    )
