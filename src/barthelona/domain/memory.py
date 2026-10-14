"""Lessons and policy models (docs/architecture.md §4 "Memory and policy", §11, §15.2)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, ConfigDict, Field, StringConstraints, field_validator, model_validator

from barthelona.domain._base import (
    Document,
    DomainModel,
    ItemId,
    PolicyVersionId,
    Sha256,
    ShortText,
    Text,
)
from barthelona.domain.enums import OS, Arch, Dialect, ObjFormat

LESSON_RULE_MAX_WORDS = 40


class LessonKind(StrEnum):
    PITFALL = "pitfall"
    RECIPE = "recipe"
    TOOLCHAIN_QUIRK = "toolchain_quirk"
    CONVENTION = "convention"


class LessonStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class LessonTrigger(DomainModel):
    error_sig: Sha256 | None = None
    terms: list[ShortText] = Field(default_factory=list, max_length=16)


class LessonScope(DomainModel):
    dialect: Dialect | None = None
    arch: Arch | None = None
    os: OS | None = None
    format: ObjFormat | None = None
    toolchain_range: ShortText | None = None  # e.g. "nasm>=2.16,<4"


class Evidence(DomainModel):
    run: ItemId
    sprint: int = Field(ge=1)
    error_before: Sha256
    diff_hash: Sha256
    verified_by: ShortText  # the oracle that accepted the fix, e.g. "V2"


class RegressionCheck(DomainModel):
    asm: Text
    cmd: list[ShortText] = Field(min_length=1, max_length=32)  # argv, never a shell string
    expect: ShortText


class Lesson(Document):
    id: ItemId
    kind: LessonKind
    rule: Text  # imperative, at most 40 words
    rationale: Text = ""
    trigger: LessonTrigger = Field(default_factory=LessonTrigger)
    scope: LessonScope = Field(default_factory=LessonScope)
    evidence: list[Evidence] = Field(default_factory=list)
    regression_check: RegressionCheck | None = None
    status: LessonStatus = LessonStatus.CANDIDATE
    alpha: float = Field(default=1.0, gt=0)  # Beta(alpha, beta) usefulness estimate
    beta: float = Field(default=1.0, gt=0)
    uses: int = Field(default=0, ge=0)
    created: datetime
    last_confirmed: datetime | None = None
    source: Literal["retro", "human", "web"]
    url: AnyHttpUrl | None = None

    @field_validator("rule")
    @classmethod
    def _short_rule(cls, value: str) -> str:
        if len(value.split()) > LESSON_RULE_MAX_WORDS:
            raise ValueError(f"a lesson rule has at most {LESSON_RULE_MAX_WORDS} words")
        return value

    @model_validator(mode="after")
    def _web_needs_url(self) -> Lesson:
        if self.source == "web" and self.url is None:
            raise ValueError("a web-sourced lesson needs its url")
        return self


class Knob(DomainModel):
    type: Literal["int", "float", "enum", "bool"]
    min: float | None = None
    max: float | None = None
    values: list[ShortText] = Field(default_factory=list)
    default: int | float | bool | str

    @model_validator(mode="after")
    def _default_in_range(self) -> Knob:
        if self.type == "enum":
            if self.default not in self.values:
                raise ValueError("enum knob default must be one of its values")
        elif self.type in ("int", "float"):
            if isinstance(self.default, bool) or not isinstance(self.default, int | float):
                raise ValueError("numeric knob needs a numeric default")
            if self.min is None or self.max is None or not self.min <= self.default <= self.max:
                raise ValueError("numeric knob needs min <= default <= max")
        elif not isinstance(self.default, bool):
            raise ValueError("bool knob needs a bool default")
        return self


class PolicyVersion(Document):
    """The manifest view of `policies/vN/`. Released versions are immutable (invariant 7)."""

    id: PolicyVersionId
    parent: PolicyVersionId | None = None
    templates: dict[str, Sha256] = Field(default_factory=dict)  # file -> sha256
    prompts: dict[str, Sha256] = Field(default_factory=dict)
    rules: Sha256 | None = None
    knobs: dict[str, Knob] = Field(default_factory=dict)
    caps: dict[str, float] = Field(default_factory=dict)
    released: bool = False
    sha256: Sha256 | None = None


class OverlayChange(Document):
    """A per-project knob change made by the retrospective; bounded and reversible (§11)."""

    project: ItemId
    knob: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    old: int | float | bool | str
    new: int | float | bool | str
    reason: ShortText
    sprint: int = Field(ge=1)


class PolicyPatchStatus(StrEnum):
    PROPOSED = "proposed"
    LAB_PASSED = "lab_passed"
    LAB_FAILED = "lab_failed"
    APPROVED = "approved"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class JsonPatchOp(DomainModel):
    """One RFC 6902 operation."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_by_name=True, serialize_by_alias=True)

    op: Literal["add", "remove", "replace", "move", "copy", "test"]
    path: Annotated[str, StringConstraints(pattern=r"^(/[^/]*)*$", max_length=255)]
    value: Any = None
    from_: Annotated[str, StringConstraints(pattern=r"^(/[^/]*)*$", max_length=255)] | None = Field(
        default=None, alias="from"
    )


class PolicyPatch(Document):
    id: ItemId
    base_version: PolicyVersionId
    kind: Literal["prompt", "rule", "template", "knob_default"]
    ops: list[JsonPatchOp] = Field(min_length=1, max_length=64)
    rationale: Text
    evidence_runs: list[ItemId] = Field(default_factory=list)
    lab_result: dict[str, float] | None = None  # metric -> value from the Policy Lab A/B
    status: PolicyPatchStatus = PolicyPatchStatus.PROPOSED
