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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from barthelona.domain.verification import Severity
from barthelona.toolchains._diagnostics import parse_assembler_output

AssembleStatus = Literal["pass", "fail", "unavailable"]
_TIMEOUT_S = 20
_MAX_ERRORS = 12
_HOST_FILE_DIRECTIVE = re.compile(r"%\s*(include|pathsearch|depend)\b|\bincbin\b", re.IGNORECASE)

_NOT_FOUND = "nasm was not found (tried --nasm, BARTHELONA_NASM, NASM_PATH, PATH, usual Windows folders)"
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


def assemble_object(
    source: str,
    nasm: str | None = None,
    runner: Runner = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> tuple[AssembleResult, bytes]:
    """The verdict on *source* and, when it is ``pass``, the relocatable object NASM produced."""
    binary = find_nasm(nasm, env)
    if binary is None:
        return AssembleResult("unavailable", (_NOT_FOUND,)), b""
    if not source.strip():
        return _fail("the source is empty"), b""
    if _HOST_FILE_DIRECTIVE.search(source):
        return _fail(
            "%include, %pathsearch, %depend and incbin are refused: they read files from the host"
        ), b""
    with tempfile.TemporaryDirectory(prefix="barthelona-asm-") as work:
        path, obj = Path(work) / "main.asm", Path(work) / "main.o"
        # S2083 is a false positive: a fixed file name in a fresh temp folder, the source is only content.
        path.write_text(source + "\n", encoding="utf-8", newline="\n")  # NOSONAR
        try:
            done = runner(
                [binary, "-f", "elf64", "-o", str(obj), str(path)],
                capture_output=True,
                timeout=_TIMEOUT_S,
                check=False,
                cwd=work,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AssembleResult("unavailable", (f"nasm did not run: {exc}",)), b""
        if done.returncode == 0:
            return AssembleResult("pass"), obj.read_bytes() if obj.is_file() else b""
    found = [d for d in parse_assembler_output("nasm", done.stderr) if d.severity is Severity.FATAL]
    errors = tuple(f"line {d.line}: {d.message}" if d.line else d.message for d in found[:_MAX_ERRORS])
    return (
        AssembleResult(
            "fail", errors or (done.stderr.decode("utf-8", "replace").strip()[:500] or "nasm failed",)
        ),
        b"",
    )


def assemble_source(
    source: str,
    nasm: str | None = None,
    runner: Runner = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> AssembleResult:
    """``pass`` when NASM accepts *source*, ``fail`` with its errors, ``unavailable`` when it cannot run."""
    return assemble_object(source, nasm, runner, env)[0]


def assemble_best(joined: str, blocks: Sequence[str], nasm: str | None = None) -> tuple[str, AssembleResult]:
    """The joined source if it assembles, else the last single block that does; NASM still decides.

    Seen live: a model restates the program in a later chunk with small changes, so the blocks joined
    define every label twice although one block alone is a valid program. Blocks with an entry point come
    first: a data-only snippet assembles too, but it is not the program.
    """
    gate = assemble_source(joined, nasm)
    if gate.status != "fail":
        return joined, gate
    tried = {joined}
    for block in sorted(reversed(blocks), key=lambda text: "_start" not in text):
        if block in tried:
            continue
        tried.add(block)
        trial = assemble_source(block, nasm)
        if trial.status == "pass":
            return block, trial
    return joined, gate
