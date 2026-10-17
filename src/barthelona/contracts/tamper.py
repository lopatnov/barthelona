"""Tamper gate: ``gen/`` must equal a fresh regeneration byte for byte (invariants 3 and 4)."""

from __future__ import annotations

import time
from pathlib import Path

from barthelona.contracts.codegen import GEN_DIR, render_all
from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import DiagnosticLevel
from barthelona.domain.verification import Diagnostic, LevelResult, Severity


def _fatal(code: str, message: str, path: str) -> Diagnostic:
    return Diagnostic(
        tool="tamper",
        level=DiagnosticLevel.TAMPER,
        severity=Severity.FATAL,
        code=code,
        message=message,
        file=path,
    )


def _content(path: Path) -> bytes:
    """File bytes; a symlink or unreadable file gets a marker that never equals generated output."""
    if path.is_symlink():
        return b"\0symlink"
    try:
        return path.read_bytes()
    except OSError:
        return b"\0unreadable"


def _present(workspace: Path) -> dict[str, bytes]:
    root = workspace / GEN_DIR
    if not root.is_dir():
        return {}
    return {
        path.relative_to(workspace).as_posix(): _content(path)
        for path in root.rglob("*")
        if path.is_symlink() or path.is_file()
    }


def check_generated(registry: ContractRegistry, workspace: Path) -> list[Diagnostic]:
    """Fatal diagnostics for each generated file that is missing, edited or not produced by codegen."""
    expected = {path: text.encode("utf-8") for path, text in render_all(registry).items()}
    present = _present(workspace)
    diagnostics = [
        _fatal("tamper.missing", f"{path} is missing; regenerate it from contracts.yaml", path)
        for path in sorted(expected.keys() - present.keys())
    ]
    diagnostics += [
        _fatal("tamper.edited", f"{path} differs from the regenerated output", path)
        for path in sorted(expected.keys() & present.keys())
        if expected[path] != present[path]
    ]
    diagnostics += [
        _fatal("tamper.extra", f"{path} is not produced by codegen", path)
        for path in sorted(present.keys() - expected.keys())
    ]
    return diagnostics


def tamper_result(registry: ContractRegistry, workspace: Path) -> LevelResult:
    started = time.monotonic()
    diagnostics = check_generated(registry, workspace)
    return LevelResult(
        level="tamper",
        status="fail" if diagnostics else "pass",
        diagnostics=diagnostics,
        secs=time.monotonic() - started,
    )
