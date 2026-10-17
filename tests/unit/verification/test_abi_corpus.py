"""The first ABI mutation corpus entries: complete, labelled, and every snippet assembles."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from barthelona.domain.enums import Level
from barthelona.executors import AgentExecutor, LocalTransport
from barthelona.toolchains import GasIntelAdapter, NasmAdapter
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification import run_ladder

_ROOT = Path(__file__).parents[2] / "abi_mutation"
_MANIFEST = YAML(typ="safe").load((_ROOT / "kinds.yaml").read_text(encoding="utf-8"))
_KINDS: dict[str, dict[str, str]] = _MANIFEST["kinds"]
_DIALECTS: dict[str, str] = _MANIFEST["dialects"]
_ADAPTERS: dict[str, type[DialectAdapter]] = {"nasm": NasmAdapter, "gas-intel": GasIntelAdapter}
_HEADER = re.compile(
    r"^[;#] dialect=(?P<dialect>\S+) preset=\S+ kind=(?P<kind>\S+) verdict=(?P<verdict>\S+)$"
)
_ENTRIES = [
    pytest.param(dialect, verdict, kind, id=f"{dialect}-{verdict}-{kind}")
    for dialect in _DIALECTS
    for verdict in ("good", "bad")
    for kind in _KINDS
]


def _path(dialect: str, verdict: str, kind: str) -> Path:
    return _ROOT / dialect / verdict / f"{kind}.{_DIALECTS[dialect]}"


@pytest.mark.parametrize(("dialect", "verdict", "kind"), _ENTRIES)
def test_every_kind_has_a_labelled_snippet_per_dialect_and_verdict(
    dialect: str, verdict: str, kind: str
) -> None:
    header = _HEADER.match(_path(dialect, verdict, kind).read_text(encoding="utf-8").splitlines()[0])
    assert header is not None
    assert header.groupdict() == {"dialect": dialect, "kind": kind, "verdict": verdict}


@pytest.mark.parametrize("dialect", list(_DIALECTS))
def test_the_corpus_holds_no_unlisted_snippet(dialect: str) -> None:
    expected = {_path(dialect, verdict, kind) for verdict in ("good", "bad") for kind in _KINDS}
    found = {path for path in (_ROOT / dialect).rglob("*") if path.is_file()}
    assert found == expected


def test_every_kind_names_its_detector() -> None:
    assert {entry["detector"] for entry in _KINDS.values()} <= {"V3", "V4", "V5"}


@pytest.mark.docker
@pytest.mark.parametrize(("dialect", "verdict", "kind"), _ENTRIES)
async def test_the_snippet_assembles(dialect: str, verdict: str, kind: str) -> None:
    executor = AgentExecutor(LocalTransport())
    try:
        results = await run_ladder(
            Level.V1,
            executor,
            _ADAPTERS[dialect](),
            [_path(dialect, verdict, kind)],
            f"abi-{dialect}-{verdict}-{kind}",
        )
    finally:
        await executor.aclose()
    assert {r.level: r.status for r in results} == {Level.V0: "pass", Level.V1: "pass"}
