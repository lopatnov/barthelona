"""Generate ``gen/<module>.inc`` from the contract registry (architecture §15.1, invariant 3).

Each module gets its exports, only its own imports, and the registry's consts and structs.
Output is deterministic, LF-only and carries a hash header so that any edit is detectable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from barthelona.contracts.symbols import called_imports, expected_exports, module_stem
from barthelona.domain.contracts import ContractRegistry, StructDef, SymbolKind
from barthelona.domain.enums import Dialect

GEN_DIR = "gen"
HEADER_MARK = "barthelona-gen v1 body-sha256="


class CodegenError(ValueError):
    """The registry cannot be rendered for its dialect."""


def _nasm_struct(name: str, struct: StructDef) -> list[str]:
    lines = [f"struc {name}"]
    if struct.fields[0].off:
        lines.append(f"    resb {struct.fields[0].off}")
    ends = [f.off for f in struct.fields[1:]] + [struct.size]
    lines += [f"    .{f.name}: resb {end - f.off}" for f, end in zip(struct.fields, ends, strict=True)]
    lines.append("endstruc")
    return lines


def _nasm_body(registry: ContractRegistry, stem: str) -> list[str]:
    lines = [f"global {name}" for name in sorted(expected_exports(registry, stem))]
    lines += [f"extern {name}" for name in sorted(called_imports(registry, stem))]
    lines += [f"{name} equ {value}" for name, value in sorted(registry.consts.items())]
    for name, struct in sorted(registry.structs.items()):
        lines += _nasm_struct(name, struct)
    return lines


def _gas_export(registry: ContractRegistry, name: str) -> list[str]:
    kind = "function" if registry.symbols[name].kind == SymbolKind.FUNC else "object"
    return [f".globl {name}", f".type {name}, @{kind}"]


def _gas_body(registry: ContractRegistry, stem: str) -> list[str]:
    lines = [
        line for name in sorted(expected_exports(registry, stem)) for line in _gas_export(registry, name)
    ]
    lines += [f".equ {name}, {value}" for name, value in sorted(registry.consts.items())]
    for name, struct in sorted(registry.structs.items()):
        lines += [f".equ {name}.{f.name}, {f.off}" for f in struct.fields]
        lines.append(f".equ {name}_size, {struct.size}")
    return lines


_RENDERERS: dict[Dialect, tuple[str, Callable[[ContractRegistry, str], list[str]]]] = {
    Dialect.NASM: (";", _nasm_body),
    Dialect.GAS_INTEL: ("#", _gas_body),
    Dialect.GAS_ATT: ("#", _gas_body),
}


def _module_stems(registry: ContractRegistry) -> list[str]:
    stems: dict[str, str] = {}
    for symbol in registry.symbols.values():
        stem = module_stem(symbol.module)
        if stems.setdefault(stem, symbol.module) != symbol.module:
            raise CodegenError(f"modules {stems[stem]!r} and {symbol.module!r} share the file stem {stem!r}")
    return sorted(stems)


def render_module_inc(registry: ContractRegistry, stem: str) -> str:
    """Text of ``gen/<stem>.inc`` for the registry's dialect."""
    try:
        comment, body_of = _RENDERERS[registry.target.dialect]
    except KeyError:
        raise CodegenError(f"no codegen for dialect {registry.target.dialect.value!r}") from None
    body = "".join(f"{line}\n" for line in body_of(registry, stem))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{comment} GENERATED from contracts.yaml, do not edit. {HEADER_MARK}{digest}\n{body}"


def render_all(registry: ContractRegistry) -> dict[str, str]:
    """Every generated file, keyed by its path relative to the workspace root."""
    return {f"{GEN_DIR}/{stem}.inc": render_module_inc(registry, stem) for stem in _module_stems(registry)}
