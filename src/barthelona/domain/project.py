"""Target and project specification models (docs/architecture.md §4 "Target and project")."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain._base import (
    Document,
    DomainModel,
    ItemId,
    RelPath,
    ShortText,
    SymbolName,
    Text,
    require_unique,
)
from barthelona.domain.enums import ABI, OS, Arch, Dialect, Level, Linker, ObjFormat, RunEnv, StoryKind

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


class TargetProfile(Document):
    """Assembler dialect plus arch / OS / ABI / format: what is built and how it is run."""

    preset: Slug  # e.g. linux-x64-nasm-static
    dialect: Dialect
    dialect_version: Annotated[str, StringConstraints(max_length=32)] = ""
    arch: Arch
    os: OS
    abi: ABI
    obj_format: ObjFormat
    link: Linker
    pie: bool = False
    entry: SymbolName | None = "_start"
    run_env: RunEnv
    dod: dict[StoryKind, Level] = Field(default_factory=dict)  # story kind -> highest required level


class Requirement(DomainModel):
    id: ItemId
    text: Text
    test_ids: list[ItemId] = Field(default_factory=list, max_length=32)


class ModuleSpec(DomainModel):
    path: RelPath
    purpose: ShortText
    exports: list[SymbolName] = Field(default_factory=list, max_length=64)
    imports: list[SymbolName] = Field(default_factory=list, max_length=64)
    max_lines: int = Field(default=250, ge=1, le=2000)
    owner_story: ItemId | None = None


class ProjectSpec(Document):
    """Create mode: the approved specification of a new project (gate G1)."""

    id: ItemId
    slug: Slug
    request_original: Text
    request_lang: Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]  # ISO 639 code
    summary_en: Text
    target: TargetProfile
    requirements: list[Requirement] = Field(default_factory=list, max_length=100)
    modules: list[ModuleSpec] = Field(default_factory=list, max_length=64)
    constraints: list[ShortText] = Field(default_factory=list, max_length=32)
    non_goals: list[ShortText] = Field(default_factory=list, max_length=32)
    assumptions: list[ShortText] = Field(default_factory=list, max_length=32)
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def _unique_ids(self) -> ProjectSpec:
        require_unique("requirement id", [r.id for r in self.requirements])
        require_unique("module path", [m.path for m in self.modules])
        return self


class ChangeSpec(Document):
    """Edit mode: what the requested change does to an existing project."""

    intent_en: Text
    requirements: list[Requirement] = Field(default_factory=list, max_length=100)
    new_test_ids: list[ItemId] = Field(default_factory=list, max_length=100)
    superseded_test_ids: list[ItemId] = Field(default_factory=list, max_length=100)
    expected_contract_deltas: list[SymbolName] = Field(default_factory=list, max_length=64)
    scope_hints: list[ShortText] = Field(default_factory=list, max_length=32)  # files and symbols named
