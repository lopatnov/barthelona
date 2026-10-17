"""Shared types for the executor abstraction (architecture §12)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Identifies which execution environment a command runs in.
ExecutorId = Literal["tc", "sandbox", "emu", "windows-native"]


@dataclass(frozen=True)
class Command:
    """An argv list plus execution context.

    Shell strings never appear here — invariant 9 of AGENTS.md.
    """

    argv: tuple[str, ...]
    cwd: str | None = None
    env: dict[str, str] | None = None
    stdin: bytes | None = None
    timeout: float = 30.0


@dataclass(frozen=True)
class ExecLimits:
    """Per-command resource caps passed by the caller."""

    timeout: float = 30.0
    max_stdout_bytes: int = 1 << 20  # 1 MiB
    max_stderr_bytes: int = 1 << 20  # 1 MiB


@dataclass
class ExecResult:
    """The outcome of a single executor command."""

    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed: float
