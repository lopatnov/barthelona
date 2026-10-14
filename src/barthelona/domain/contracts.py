"""Contract registry models: the schema of `contracts.yaml` (docs/architecture.md §4 "Contracts", §15.1).

`contracts.yaml` is the single source of truth for interfaces (invariant 3); `gen/` is generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain._base import Document, DomainModel, ItemId, RelPath, Sha256, ShortText, SymbolName
from barthelona.domain.project import TargetProfile

Register = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]{1,7}$")]  # rax, xmm0, r12d, x0
TypeName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_ *\[\]]{0,47}$")]  # u64, char*


class SymbolKind(StrEnum):
    FUNC = "func"
    DATA = "data"
    CONST = "const"
    MACRO = "macro"
    STRUCT = "struct"


class Visibility(StrEnum):
    GLOBAL = "global"
    LOCAL = "local"
    EXTERN = "extern"


class SymbolStatus(StrEnum):
    PLANNED = "planned"
    STUB = "stub"
    IMPLEMENTED = "implemented"
    TESTED = "tested"
    INFERRED = "inferred"


class RegisterContract(DomainModel):
    reg: Register
    type: TypeName
    desc: ShortText = ""


class StackContract(DomainModel):
    entry_align: Literal["8 mod 16", "0 mod 16", "4 mod 16", "0 mod 8", "0 mod 4"] = "8 mod 16"
    # Deepest stack use in bytes; leaving it unset means the depth is not checked.
    max_depth: int | None = Field(default=None, ge=0, le=1 << 20)
    red_zone: bool = True


class MemEffect(DomainModel):
    arg: Register | SymbolName
    access: Literal["r", "w", "rw"]
    size_expr: Annotated[str, StringConstraints(min_length=1, max_length=64)]  # e.g. "rsi", "8*rdx"


class Symbol(DomainModel):
    name: SymbolName
    kind: SymbolKind
    module: RelPath  # ModuleSpec.path of the defining module
    visibility: Visibility = Visibility.GLOBAL
    abi: Literal["target", "custom"] = "target"
    inputs: list[RegisterContract] = Field(default_factory=list, max_length=16)
    outputs: list[RegisterContract] = Field(default_factory=list, max_length=8)
    flags_out: dict[Literal["CF", "ZF", "SF", "OF", "PF", "AF", "DF"], ShortText] = Field(
        default_factory=dict
    )
    clobbers: list[Register] = Field(default_factory=list, max_length=32)
    stack: StackContract = Field(default_factory=StackContract)
    mem_effects: list[MemEffect] = Field(default_factory=list, max_length=16)
    preconditions: list[ShortText] = Field(default_factory=list, max_length=16)
    calls: list[SymbolName] = Field(default_factory=list, max_length=64)
    status: SymbolStatus = SymbolStatus.PLANNED
    test_ids: list[ItemId] = Field(default_factory=list, max_length=64)
    hash: Sha256 | None = None  # set by the registry; a change marks dependent modules stale


class StructField(DomainModel):
    name: SymbolName
    type: TypeName
    off: int = Field(ge=0)


class StructDef(DomainModel):
    fields: list[StructField] = Field(min_length=1, max_length=64)
    size: int = Field(ge=1)

    @model_validator(mode="after")
    def _offsets_in_bounds(self) -> StructDef:
        offsets = [f.off for f in self.fields]
        # Field widths depend on the dialect's type sizes, so extent overflow is checked by codegen.
        if any(a >= b for a, b in pairwise(offsets)):
            raise ValueError("struct field offsets must be strictly ascending")
        if offsets[-1] >= self.size:
            raise ValueError("struct field offset beyond the struct size")
        return self


class ContractRegistry(Document):
    version: int = Field(ge=1)
    target: TargetProfile
    symbols: dict[SymbolName, Symbol] = Field(default_factory=dict)
    structs: dict[SymbolName, StructDef] = Field(default_factory=dict)
    consts: dict[SymbolName, int] = Field(default_factory=dict)
    frozen: list[SymbolName] = Field(default_factory=list)
    hash: Sha256 | None = None

    @model_validator(mode="after")
    def _consistent(self) -> ContractRegistry:
        for key, symbol in self.symbols.items():
            if symbol.name != key:
                raise ValueError(f"symbol key {key!r} does not match its name {symbol.name!r}")
        unknown = [name for name in self.frozen if name not in self.symbols]
        if unknown:
            raise ValueError(f"frozen symbols not in the registry: {unknown}")
        return self
