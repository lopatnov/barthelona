"""Test, diagnostic and verification-report models (docs/architecture.md §4 "Tests and verification", §13)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from barthelona.domain._base import (
    Document,
    DomainModel,
    ItemId,
    RelPath,
    Sha256,
    ShortText,
    SymbolName,
    Text,
)
from barthelona.domain.enums import DiagnosticLevel, Level

# Values crossing the emulator / harness boundary: integers, byte strings as hex, or text.
TestValue = int | str | list[int]


class TestKind(StrEnum):
    __test__ = False  # not a pytest class

    EMU_CALL = "emu_call"
    ABI_CONFORMANCE = "abi_conformance"
    C_HARNESS = "c_harness"
    IO_GOLDEN = "io_golden"
    DIFFERENTIAL = "differential"
    BOOT = "boot"


class TestOrigin(StrEnum):
    __test__ = False

    USER = "user"
    SPEC_AGENT = "spec_agent"
    TEST_AUTHOR = "test_author"
    CHARACTERIZATION = "characterization"
    BENCH = "bench"


class Expectation(DomainModel):
    ret: TestValue | None = None
    regs: dict[str, TestValue] = Field(default_factory=dict)
    mem: dict[str, TestValue] = Field(default_factory=dict)  # symbol or address expression -> bytes
    stdout: str | None = None
    stdout_contains: list[ShortText] = Field(default_factory=list, max_length=16)  # texts stdout must hold
    exit_code: int | None = None


class Generator(DomainModel):
    """Property-style cases: `count` inputs drawn from `domains` with a fixed seed."""

    seed: int
    count: int = Field(ge=1, le=10_000)
    domains: dict[str, ShortText] = Field(default_factory=dict)  # input name -> value domain


class TestCase(Document):
    __test__ = False

    id: ItemId
    kind: TestKind
    symbol: SymbolName | None = None
    level: Level
    inputs: dict[str, TestValue] = Field(default_factory=dict)
    expect: Expectation = Field(default_factory=Expectation)
    reference: RelPath | None = None  # Python reference model
    generator: Generator | None = None
    visibility: Literal["visible", "hidden"] = "visible"
    origin: TestOrigin
    approved: bool = False
    locked: bool = True  # tests are frozen while coding (invariant 4)
    sha256: Sha256 | None = None


class Severity(StrEnum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


class Diagnostic(DomainModel):
    tool: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    level: DiagnosticLevel
    severity: Severity
    code: Annotated[str, StringConstraints(max_length=64)] | None = None  # A2008, abi.misaligned_call
    message: Text
    file: RelPath | None = None
    line: int | None = Field(default=None, ge=1)
    macro_stack: list[ShortText] = Field(default_factory=list, max_length=16)
    symbol: SymbolName | None = None
    error_sig: Sha256 | None = None  # normalized signature for stall detection and lessons
    raw_ref: ShortText | None = None  # pointer to the raw tool output under var/runs


class LevelResult(DomainModel):
    level: Level | Literal["tamper", "minimality"]
    status: Literal["pass", "fail", "skipped", "unsupported"]
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    secs: float = Field(ge=0)


class VerificationReport(Document):
    levels: list[LevelResult] = Field(default_factory=list)
    tests_passed: list[ItemId] = Field(default_factory=list)
    tests_failed: list[ItemId] = Field(default_factory=list)
    toolchain_versions: dict[str, ShortText] = Field(default_factory=dict)


class Increment(Document):
    sprint_no: int = Field(ge=1)
    branch: Annotated[str, StringConstraints(pattern=r"^bart/[A-Za-z0-9_.-]{1,64}$")]
    git_sha: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    tag: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    stories_done: list[ItemId] = Field(default_factory=list)
    contracts_version: int = Field(ge=1)
    frozen_symbols: list[SymbolName] = Field(default_factory=list)
    report: VerificationReport
    artifacts: dict[RelPath, Sha256] = Field(default_factory=dict)
    image_digest: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")] | None = None
