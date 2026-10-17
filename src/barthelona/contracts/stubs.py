"""Generate ``gen/stubs/<module>`` skeletons from the contract registry (architecture §15.1, step 7-8).

A stub exports every function its module owns and traps if it is ever run (``ud2``), so an
unimplemented symbol fails loudly instead of returning a plausible value. The all-stub project must pass
V0-V2 before any model writes code, which proves the generators and the toolchain.
"""

from __future__ import annotations

from barthelona.contracts._gen import GEN_DIR, CodegenError, stamp
from barthelona.contracts.symbols import expected_exports
from barthelona.domain.contracts import ContractRegistry, SymbolKind
from barthelona.domain.enums import Dialect

STUB_DIR = f"{GEN_DIR}/stubs"
_NASM_NOTE = "section .note.GNU-stack noalloc noexec nowrite progbits"
_GAS_NOTE = '.section .note.GNU-stack,"",@progbits'


def stub_extension(dialect: Dialect) -> str:
    if dialect == Dialect.NASM:
        return ".asm"
    if dialect in (Dialect.GAS_INTEL, Dialect.GAS_ATT):
        return ".s"
    raise CodegenError(f"no stubs for dialect {dialect.value!r}")


def _functions(registry: ContractRegistry, stem: str) -> list[str]:
    exports = expected_exports(registry, stem)
    return sorted(name for name in exports if registry.symbols[name].kind == SymbolKind.FUNC)


def _nasm_stub(names: list[str]) -> list[str]:
    lines = ["bits 64", *(f"global {name}" for name in names), "section .text"]
    for name in names:
        lines += [f"{name}:", "    ud2"]
    return [*lines, _NASM_NOTE]


def _gas_stub(names: list[str], intel: bool) -> list[str]:
    lines = [".intel_syntax noprefix"] if intel else []
    lines.append(".text")
    for name in names:
        lines += [
            f".globl {name}",
            f".type {name}, @function",
            f"{name}:",
            "    ud2",
            f".size {name}, .-{name}",
        ]
    return [*lines, _GAS_NOTE]


def render_stub(registry: ContractRegistry, stem: str) -> str | None:
    """Text of the stub of module *stem*, or None when the module owns no function."""
    names = _functions(registry, stem)
    if not names:
        return None
    dialect = registry.target.dialect
    stub_extension(dialect)  # rejects dialects without codegen before rendering
    if dialect == Dialect.NASM:
        return stamp(";", _nasm_stub(names))
    return stamp("#", _gas_stub(names, intel=dialect == Dialect.GAS_INTEL))
