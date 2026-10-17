"""The all-stub skeleton generated from a contracts.yaml builds (Phase 0 exit criterion)."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.contracts import load_registry, render_all
from barthelona.domain.enums import Level
from barthelona.executors import AgentExecutor, LocalTransport
from barthelona.toolchains import GasIntelAdapter, NasmAdapter
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification import LadderOptions, run_ladder

_PROJECTS = Path(__file__).parents[2] / "projects"
_CASES = [
    pytest.param("nasm-triple", NasmAdapter, id="nasm"),
    pytest.param("gas-triple", GasIntelAdapter, id="gas-intel"),
]


def _stub_files(name: str, workspace: Path) -> tuple[list[Path], list[str]]:
    """Write the generated stubs of project *name* into *workspace*; return them and the module names."""
    registry = load_registry(_PROJECTS / name / "contracts.yaml")
    paths = []
    for relative, text in render_all(registry).items():
        if relative.startswith("gen/stubs/"):
            path = workspace / Path(relative).name
            path.write_text(text, encoding="utf-8", newline="\n")
            paths.append(path)
    return sorted(paths), sorted(Path(s.module).stem for s in registry.symbols.values())


@pytest.mark.parametrize(("name", "adapter"), _CASES)
def test_every_module_of_the_project_gets_a_stub(
    name: str,
    adapter: type[DialectAdapter],  # shared parameter table
    tmp_path: Path,
) -> None:
    paths, modules = _stub_files(name, tmp_path)
    assert [path.stem for path in paths] == sorted(modules)


@pytest.mark.docker
@pytest.mark.parametrize(("name", "adapter"), _CASES)
async def test_the_all_stub_skeleton_passes_v0_to_v2(
    name: str, adapter: type[DialectAdapter], tmp_path: Path
) -> None:
    paths, _ = _stub_files(name, tmp_path)
    registry = load_registry(_PROJECTS / name / "contracts.yaml")
    executor = AgentExecutor(LocalTransport())
    try:
        options = LadderOptions(contracts=registry)
        results = await run_ladder(Level.V2, executor, adapter(), paths, f"skeleton-{name}", 0, options)
    finally:
        await executor.aclose()
    assert {r.level: r.status for r in results} == dict.fromkeys([Level.V0, Level.V1, Level.V2], "pass")
