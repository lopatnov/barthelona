"""Code-change models (docs/architecture.md §4 "Code changes", §16.3).

A `Patch` is parsed from FILE / SEARCH-REPLACE / SYMBOL text envelopes. Code never travels inside JSON
(invariant 5): these models are in-memory only and are never part of an LLM-facing JSON schema.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from barthelona.domain._base import DomainModel, RelPath, SymbolName

MAX_SOURCE_CHARS = 512_000
Source = Annotated[str, StringConstraints(max_length=MAX_SOURCE_CHARS)]


class FileWrite(DomainModel):
    op: Literal["file"] = "file"
    path: RelPath
    content: Source


class HunkEdit(DomainModel):
    op: Literal["hunk"] = "hunk"
    path: RelPath
    search: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SOURCE_CHARS)]
    replace: Source


class SymbolEdit(DomainModel):
    op: Literal["symbol"] = "symbol"
    path: RelPath
    symbol: SymbolName
    new_text: Source


PatchOp = Annotated[FileWrite | HunkEdit | SymbolEdit, Field(discriminator="op")]


class Patch(DomainModel):
    ops: list[PatchOp] = Field(min_length=1, max_length=64)
