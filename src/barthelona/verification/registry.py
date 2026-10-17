"""Registered ladder checks, selected by target family (D-046, architecture §13.1).

A level id (V0..V8) is a stable name; its implementation is a :class:`LevelCheck`
registered for a target family such as ``native-asm``.  A family that cannot
check a level reports it as unsupported, so a required level that cannot run
never counts as passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import Level, Linker, ObjFormat
from barthelona.domain.verification import LevelResult, TestCase
from barthelona.executors.protocol import Session
from barthelona.toolchains.dialect import DialectAdapter

NATIVE_ASM = "native-asm"


@dataclass
class LadderContext:
    """Everything a check needs; ``object_paths`` carries V1's output to V2."""

    session: Session
    adapter: DialectAdapter
    source_files: list[Path]
    obj_format: ObjFormat = ObjFormat.ELF64
    linker: Linker = Linker.LD
    entry: str = "_start"
    contracts: ContractRegistry | None = None
    sandbox: Session | None = None  # session in bart-run over the same work directory
    tests: list[TestCase] = field(default_factory=list)
    object_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Unsupported:
    reason: str


class LevelCheck(Protocol):
    """One level's implementation for one target family."""

    level: Level
    always_run: bool  # still runs after an earlier failure; never turns that failure into a pass

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        """``None`` when the check can run for this target, else why not."""
        ...

    async def run(self, ctx: LadderContext) -> LevelResult: ...


class CheckRegistry:
    """Checks keyed by target family, then level."""

    def __init__(self) -> None:
        self._checks: dict[str, dict[Level, LevelCheck]] = {}

    def register(self, family: str, check: LevelCheck) -> None:
        family_checks = self._checks.setdefault(family, {})
        if check.level in family_checks:
            raise ValueError(f"{family}: a check for {check.level} is already registered")
        family_checks[check.level] = check

    def get(self, family: str, level: Level) -> LevelCheck | None:
        return self._checks.get(family, {}).get(level)

    def families(self) -> list[str]:
        return sorted(self._checks)
