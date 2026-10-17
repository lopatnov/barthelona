"""Contract registry: loading ``contracts.yaml`` and checking objects against it (architecture §15.1)."""

from barthelona.contracts.loader import ContractsError, load_registry
from barthelona.contracts.symbols import ObjectSymbols, check_object_symbols, parse_nm

__all__ = [
    "ContractsError",
    "ObjectSymbols",
    "check_object_symbols",
    "load_registry",
    "parse_nm",
]
