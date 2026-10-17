"""C side of the generated files: ``gen/contracts.h`` and the V5 harnesses (architecture §15.1, §13.1).

The C compiler applies the target ABI, so a harness calls each function with its declared
inputs in order and compares the first output with the expected return value.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from barthelona.contracts._gen import CodegenError, stamp
from barthelona.domain.contracts import ContractRegistry, Symbol, SymbolKind, Visibility
from barthelona.domain.enums import ABI, Arch, Level
from barthelona.domain.verification import TestCase, TestKind

_TYPE = re.compile(r"(?P<base>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<stars>(?:\*\s*)*)")
_SCALARS = {
    "u8": "uint8_t",
    "u16": "uint16_t",
    "u32": "uint32_t",
    "u64": "uint64_t",
    "i8": "int8_t",
    "i16": "int16_t",
    "i32": "int32_t",
    "i64": "int64_t",
    "usize": "size_t",
    "void": "void",
}
_BITS = {"u8": 8, "u16": 16, "u32": 32, "u64": 64, "i8": 8, "i16": 16, "i32": 32, "i64": 64, "usize": 64}
_INT_MAX = 2**31 - 1
_INT_MIN = -(2**31)
# Integer argument registers in call order, and every spelling of each (sub-registers included).
_ARG_SLOTS = {
    ABI.SYSV64: ("rdi", "rsi", "rdx", "rcx", "r8", "r9"),
    ABI.WIN64: ("rcx", "rdx", "r8", "r9"),
}
_ALIASES = {
    "rdi": "rdi edi di dil",
    "rsi": "rsi esi si sil",
    "rdx": "rdx edx dx dl",
    "rcx": "rcx ecx cx cl",
    "r8": "r8 r8d r8w r8b",
    "r9": "r9 r9d r9w r9b",
}
_CANONICAL = {name: base for base, names in _ALIASES.items() for name in names.split()}
_RETURN_REGS = frozenset({"rax", "eax", "ax", "al"})


def c_type(type_name: str) -> str:
    """C spelling of a register type: a known scalar or ``char``, optionally behind pointers."""
    match = _TYPE.fullmatch(type_name)
    if match is None or (match["base"] not in _SCALARS and match["base"] != "char"):
        raise CodegenError(f"no C type for {type_name!r}")
    stars = match["stars"].replace(" ", "")
    return f"{_SCALARS.get(match['base'], match['base'])}{' ' if stars else ''}{stars}"


def _prototype_or_skip(symbol: Symbol) -> str:
    """The prototype, or a comment saying why none is emitted (the harness for it would be refused)."""
    try:
        return _prototype(symbol)
    except CodegenError as exc:
        return f"// {symbol.name}: no prototype ({exc})"


def _prototype(symbol: Symbol) -> str:
    if symbol.abi != "target":
        raise CodegenError(f"{symbol.name} uses a custom ABI, which C cannot call")
    ret = c_type(symbol.outputs[0].type) if symbol.outputs else "void"
    args = ", ".join(f"{c_type(i.type)} a{n}" for n, i in enumerate(symbol.inputs)) or "void"
    return f"{ret} {symbol.name}({args});"


def _constant(name: str, value: int) -> str:
    if _INT_MIN <= value <= _INT_MAX:
        return f"enum {{ {name} = {value} }};"
    return f"#define {name} {_literal(value, unsigned=value > 2**63 - 1)}"


def render_contracts_h(registry: ContractRegistry) -> str:
    """Prototypes of the global functions, plus consts and struct offsets as constants."""
    lines = ["#pragma once", "#include <stddef.h>", "#include <stdint.h>"]
    lines += [_constant(name, value) for name, value in sorted(registry.consts.items())]
    for name, struct in sorted(registry.structs.items()):
        lines += [_constant(f"{name}_{f.name}", f.off) for f in struct.fields]
        lines.append(_constant(f"{name}_size", struct.size))
    lines += [
        _prototype_or_skip(symbol)
        for _, symbol in sorted(registry.symbols.items())
        if symbol.kind == SymbolKind.FUNC and symbol.visibility == Visibility.GLOBAL
    ]
    return stamp("//", lines)


def c_harness_cases(tests: Sequence[TestCase]) -> list[TestCase]:
    return [t for t in tests if t.kind == TestKind.C_HARNESS and t.level == Level.V5]


def _literal(value: int, *, unsigned: bool) -> str:
    if value == -(2**63):
        raise CodegenError("-2**63 has no portable C literal; use a different value")
    return f"{value}{'ULL' if unsigned else 'LL'}"


def _integer(case: TestCase, what: str, value: object, type_name: str) -> str:
    """A C literal for an integer of the given register type; refuses non-integers and out-of-range values."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodegenError(f"{case.id}: {what} must be an integer, got {value!r}")
    bits, unsigned = _BITS[type_name], type_name.startswith(("u", "usize"))
    low, high = (0, 2**bits - 1) if unsigned else (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
    if not low <= value <= high:
        raise CodegenError(f"{case.id}: {what} {value} does not fit {type_name}")
    return _literal(value, unsigned=unsigned)


def _check_callable(case: TestCase, symbol: Symbol, registry: ContractRegistry) -> None:
    """Refuse symbols whose register contract C cannot reproduce, instead of building a wrong harness."""
    target = registry.target
    slots = _ARG_SLOTS.get(target.abi) if target.arch == Arch.X86_64 else None
    if slots is None:
        raise CodegenError(f"{case.id}: no C harness for {target.arch.value}/{target.abi.value}")
    _prototype(symbol)
    if symbol.flags_out:
        raise CodegenError(f"{case.id}: flags cannot be observed from C; test {symbol.name} at V4")
    if len(symbol.outputs) != 1 or symbol.outputs[0].reg not in _RETURN_REGS:
        raise CodegenError(f"{case.id}: {symbol.name} must return exactly one value in rax")
    if len(symbol.inputs) > len(slots):
        raise CodegenError(f"{case.id}: {symbol.name} has more inputs than argument registers")
    for slot, item in zip(slots, symbol.inputs, strict=False):
        if _CANONICAL.get(item.reg) != slot:
            raise CodegenError(f"{case.id}: input {item.reg} of {symbol.name} is not in {slot}")
    for item in [*symbol.inputs, *symbol.outputs]:
        if item.type not in _BITS:
            raise CodegenError(f"{case.id}: {symbol.name} {item.reg} has non-integer type {item.type!r}")


def render_harness(registry: ContractRegistry, case: TestCase) -> str:
    """A ``main`` that calls the tested function and returns 1 when the result differs.

    It checks the return value only; callee-saved registers, flags and memory are V3/V4 concerns.
    """
    if case.symbol is None or case.symbol not in registry.symbols:
        raise CodegenError(f"{case.id}: symbol {case.symbol!r} is not in the registry")
    symbol = registry.symbols[case.symbol]
    if case.expect.ret is None:
        raise CodegenError(f"{case.id}: a c_harness case needs expect.ret")
    if (
        case.expect.regs
        or case.expect.mem
        or case.expect.stdout is not None
        or case.expect.exit_code is not None
    ):
        raise CodegenError(f"{case.id}: a c_harness case checks only expect.ret")
    extra = sorted(set(case.inputs) - {i.reg for i in symbol.inputs})
    if extra:
        raise CodegenError(f"{case.id}: inputs {extra} are not inputs of {symbol.name}")
    _check_callable(case, symbol, registry)
    args = ", ".join(_integer(case, f"input {i.reg}", case.inputs.get(i.reg), i.type) for i in symbol.inputs)
    ret_type = symbol.outputs[0].type
    want = _integer(case, "expect.ret", case.expect.ret, ret_type)
    wide, fmt = (
        ("unsigned long long", "%llu") if ret_type.startswith(("u", "usize")) else ("long long", "%lld")
    )
    lines = [
        "#include <stdio.h>",
        '#include "../contracts.h"',
        "int main(void) {",
        f"    {wide} got = ({wide}){symbol.name}({args});",
        f"    {wide} want = {want};",
        "    if (got != want) {",
        f'        printf("{case.id}: got {fmt}, want {fmt}\\n", got, want);',
        "        return 1;",
        "    }",
        "    return 0;",
        "}",
    ]
    return stamp("//", lines)
