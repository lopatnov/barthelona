"""The two hand-written 3-module projects pass V0-V2, V5 and V6 (Phase 0 exit criterion)."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.contracts import load_registry, load_test_cases
from barthelona.domain.enums import Level
from barthelona.executors import AgentExecutor, LocalTransport
from barthelona.toolchains import GasIntelAdapter, NasmAdapter
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification import LadderOptions, dod_satisfied, run_ladder

_PROJECTS = Path(__file__).parents[2] / "projects"
_REQUIRED = [Level.V0, Level.V1, Level.V2, Level.V5, Level.V6]
_CASES = [
    pytest.param("nasm-triple", ".asm", NasmAdapter, id="nasm"),
    pytest.param("gas-triple", ".s", GasIntelAdapter, id="gas-intel"),
]


@pytest.mark.parametrize(("name", "extension", "adapter"), _CASES)
def test_the_project_has_three_modules_and_loadable_contracts(
    name: str,
    extension: str,
    adapter: type[DialectAdapter],  # shared parameter table
) -> None:
    directory = _PROJECTS / name
    registry = load_registry(directory / "contracts.yaml")
    tests = load_test_cases(directory / "tests.yaml")
    modules = {Path(symbol.module).name for symbol in registry.symbols.values()}
    assert modules == {f"main{extension}", f"io{extension}", f"math{extension}"}
    assert {path.name for path in directory.glob(f"*{extension}")} == modules
    assert {test.level for test in tests} == {Level.V5, Level.V6}


@pytest.mark.docker
@pytest.mark.parametrize(("name", "extension", "adapter"), _CASES)
async def test_the_project_passes_the_ladder_through_v6(
    name: str, extension: str, adapter: type[DialectAdapter]
) -> None:
    directory = _PROJECTS / name
    sources = sorted(directory.glob(f"*{extension}"))
    executor = AgentExecutor(LocalTransport())
    try:
        options = LadderOptions(
            contracts=load_registry(directory / "contracts.yaml"),
            tests=load_test_cases(directory / "tests.yaml"),
            sandbox=executor.sandbox(),
        )
        results = await run_ladder(Level.V6, executor, adapter(), sources, f"project-{name}", 0, options)
    finally:
        await executor.aclose()
    by_level = {r.level: r.status for r in results}
    assert {level: by_level[level] for level in _REQUIRED} == dict.fromkeys(_REQUIRED, "pass")
    assert dod_satisfied(_REQUIRED, results)
