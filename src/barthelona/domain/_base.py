"""Base classes and shared field types for the domain models (docs/architecture.md §4)."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

import orjson
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION: Literal[1] = 1

# Node, task and template ids (validator rule T2, §9.4).
NODE_ID_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"
NodeId = Annotated[str, StringConstraints(pattern=NODE_ID_PATTERN)]
# Story, requirement, test and lesson ids: short, stable, safe in paths and git refs.
ItemId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
# Assembly symbol names: C-like identifiers plus `.`, `$` and `@`, which NASM and GAS accept.
SymbolName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_.$@?][A-Za-z0-9_.$@?]{0,127}$")]
PolicyVersionId = Annotated[str, StringConstraints(pattern=r"^v[1-9][0-9]{0,4}$")]  # policies/vN
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _check_rel_path(value: str) -> str:
    if "\\" in value or ":" in value or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValueError("path must be POSIX, without backslashes, control characters or drive letters")
    if value.startswith("/"):
        raise ValueError("path must be relative to the workspace")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("path must not contain empty, '.' or '..' segments")
    return value


# Workspace-relative POSIX path (also used for write-scope globs).
RelPath = Annotated[str, StringConstraints(min_length=1, max_length=255), AfterValidator(_check_rel_path)]
ShortText = Annotated[str, StringConstraints(max_length=200)]
Text = Annotated[str, StringConstraints(max_length=4000)]


class DomainModel(BaseModel):
    """Value object: fields cannot be reassigned and unknown keys are rejected.

    `model_copy(update=...)` skips validation, so use it only for trusted values; build untrusted updates
    with `model_validate(model.model_dump() | changes)`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class Document(DomainModel):
    """A top-level artifact that is persisted or exchanged on its own.

    It carries `schema_version`; nested value objects take the version of the document that holds them.
    """

    schema_version: Literal[1] = Field(default=SCHEMA_VERSION)


# A model's own hash fields are not part of what they hash.
HASH_FIELDS = frozenset({"hash", "spec_hash", "sha256"})


def canonical_json(model: BaseModel) -> bytes:
    """Canonical JSON for hashing: JSON mode, sorted keys, no whitespace, top-level hash fields left out."""
    data = model.model_dump(mode="json", exclude=set(HASH_FIELDS & set(type(model).model_fields)))
    return orjson.dumps(data, option=orjson.OPT_SORT_KEYS)


def spec_hash(model: BaseModel) -> str:
    """sha256 of `canonical_json` (rule T2); unchanged when the model's own hash field is filled in."""
    return hashlib.sha256(canonical_json(model)).hexdigest()


def require_unique(what: str, values: list[str]) -> None:
    """Raise `ValueError` naming the first repeated value."""
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {what}: {value}")
        seen.add(value)
