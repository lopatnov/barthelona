"""Assemble model-written NASM source on the host: the oracle that decides a ``chunked run`` result.

The source is only assembled (``nasm -f elf64``), never linked or run (invariant 2). Directives that make
the assembler read host files are refused first, because the text comes from a model. This is a stopgap for
runs outside the ladder; the real path is the sandboxed V0-V2 levels (roadmap follow-up on #206).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # argv list only, never a shell (invariant 9)
import tempfile
from collections.abc import Callable, Mapping
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


def _resolve(hint: str) -> str | None:
    """A nasm binary from a file path or from a folder that holds one (NASM_PATH is usually the folder)."""
    path = Path(hint)
    if path.is_file():
        return str(path)
    for name in ("nasm.exe", "nasm"):
        if (path / name).is_file():
            return str(path / name)
    return shutil.which(hint) if os.sep not in hint and "/" not in hint else None


def _usual_windows_folders(env: Mapping[str, str]) -> list[str]:
    local = env.get("LOCALAPPDATA", "")
    folders = [f"{local}/bin/NASM", f"{local}/Programs/NASM"] if local else []
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if base := env.get(name, ""):
            folders.append(f"{base}/NASM")
    return folders


def find_nasm(explicit: str | None = None, env: Mapping[str, str] | None = None) -> str | None:
    """--nasm wins and must exist; then BARTHELONA_NASM, NASM_PATH, PATH and the usual Windows folders."""
    env = os.environ if env is None else env
    if explicit:
        return _resolve(explicit)
    hints = [env.get("BARTHELONA_NASM", ""), env.get("NASM_PATH", ""), "nasm", *_usual_windows_folders(env)]
    return next((found for hint in hints if hint and (found := _resolve(hint))), None)


def assemble_source(
    source: str,
    nasm: str | None = None,
    runner: Runner = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> AssembleResult:
    """``pass`` when NASM accepts *source*, ``fail`` with its errors, ``unavailable`` when it cannot run."""
    binary = find_nasm(nasm, env)
    if binary is None:
        return AssembleResult(
            "unavailable",
            ("nasm was not found (tried --nasm, BARTHELONA_NASM, NASM_PATH, PATH, usual Windows folders)",),
        )
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
