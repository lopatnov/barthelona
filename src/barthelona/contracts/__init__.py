"""Contract registry: loading ``contracts.yaml`` and checking objects against it (architecture §15.1)."""

from barthelona.contracts.codegen import CodegenError, render_all, render_module_inc
from barthelona.contracts.loader import ContractsError, load_registry, load_test_cases
from barthelona.contracts.symbols import ObjectSymbols, check_object_symbols, parse_nm
from barthelona.contracts.tamper import check_generated, tamper_result

__all__ = [
    "CodegenError",
    "ContractsError",
    "ObjectSymbols",
    "check_generated",
    "check_object_symbols",
    "load_registry",
    "load_test_cases",
    "parse_nm",
    "render_all",
    "render_module_inc",
    "tamper_result",
]
