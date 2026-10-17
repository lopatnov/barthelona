"""V1 symbol check: an object file's ``nm`` symbols against the contract registry (architecture §13.1).

Exports must match the registry exactly; undefined symbols must be imports the
registry declares or an allow-listed linker symbol.  The parser reads the
portable ``nm -P -g`` format (``name type [value [size]]``); its fixtures are
real captured output under ``tests/fixtures/diagnostics/nm/``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from barthelona.domain.contracts import ContractRegistry, SymbolKind, Visibility
from barthelona.domain.enums import DiagnosticLevel
from barthelona.domain.verification import Diagnostic, Severity

_UNDEFINED_TYPES = frozenset("Uvw")
_EXPORT_KINDS = frozenset({SymbolKind.FUNC, SymbolKind.DATA})

DEFAULT_ALLOW_LIST: frozenset[str] = frozenset({"_GLOBAL_OFFSET_TABLE_"})


@dataclass(frozen=True)
class ObjectSymbols:
    defined: frozenset[str]
    undefined: frozenset[str]


def parse_nm(output: bytes) -> ObjectSymbols:
    """Parse ``nm -P -g`` output; malformed lines are ignored."""
    defined: set[str] = set()
    undefined: set[str] = set()
    for line in output.decode("utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 2 or len(fields[1]) != 1:
            continue
        name, symbol_type = fields[0], fields[1]
        (undefined if symbol_type in _UNDEFINED_TYPES else defined).add(name)
    return ObjectSymbols(frozenset(defined), frozenset(undefined))


def module_stem(module: str) -> str:
    return Path(module).stem


def expected_exports(registry: ContractRegistry, stem: str) -> frozenset[str]:
    return frozenset(
        name
        for name, symbol in registry.symbols.items()
        if module_stem(symbol.module) == stem
        and symbol.visibility == Visibility.GLOBAL
        and symbol.kind in _EXPORT_KINDS
    )


def _own_symbols(registry: ContractRegistry, stem: str) -> set[str]:
    return {name for name, symbol in registry.symbols.items() if module_stem(symbol.module) == stem}


def called_imports(registry: ContractRegistry, stem: str) -> frozenset[str]:
    """Foreign names the module's own symbols call: the only imports its generated header declares."""
    own = _own_symbols(registry, stem)
    return frozenset({callee for name in own for callee in registry.symbols[name].calls} - own)


def declared_imports(registry: ContractRegistry, stem: str) -> frozenset[str]:
    """Names the module may leave undefined: what its symbols call, plus explicit externs."""
    own = _own_symbols(registry, stem)
    externs = {
        name
        for name, symbol in registry.symbols.items()
        if symbol.visibility == Visibility.EXTERN and name not in own
    }
    return called_imports(registry, stem) | frozenset(externs)


def _fatal(message: str, source: str, symbol: str) -> Diagnostic:
    return Diagnostic(
        tool="nm",
        level=DiagnosticLevel.V1,
        severity=Severity.FATAL,
        code="symbols.mismatch",
        message=message,
        file=source,
        symbol=symbol,
    )


def check_object_symbols(
    registry: ContractRegistry,
    source: str,
    found: ObjectSymbols,
    allow_list: Iterable[str] = DEFAULT_ALLOW_LIST,
) -> list[Diagnostic]:
    """Diagnostics for one object: unregistered or missing exports, undeclared imports."""
    stem = module_stem(source)
    expected = expected_exports(registry, stem)
    permitted = declared_imports(registry, stem) | frozenset(allow_list)
    diagnostics = [
        _fatal(f"{source} defines global symbol {name!r} that is not in the registry", source, name)
        for name in sorted(found.defined - expected)
    ]
    diagnostics += [
        _fatal(f"{source} does not define registry symbol {name!r}", source, name)
        for name in sorted(expected - found.defined)
    ]
    diagnostics += [
        _fatal(f"{source} references undeclared symbol {name!r}", source, name)
        for name in sorted(found.undefined - permitted)
    ]
    return diagnostics
