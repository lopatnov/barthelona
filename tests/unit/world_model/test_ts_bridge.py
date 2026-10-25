"""The slow integration test: the Python World Model agrees with the real TypeScript implementation (D-058).

It runs `engines/world-model/index.ts` through `npx tsx` when Node is available and skips otherwise. The two
implementations must derive the same stable IDs and both report an empty diff on re-ingest.
"""

from __future__ import annotations

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Expectation,
    Level,
    Linker,
    ObjFormat,
    ProjectSpec,
    Requirement,
    RunEnv,
    TargetProfile,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.world_model import record_spec_and_tests
from barthelona.world_model.bridge import TsWorldModel, TsWorldModelUnavailable, is_available

pytestmark = pytest.mark.slow


def _spec() -> ProjectSpec:
    target = TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=Dialect.NASM,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    return ProjectSpec(
        id="s1",
        slug="hello",
        request_original="Print hello.",
        request_lang="en",
        summary_en="Prints hello.",
        target=target,
        requirements=[Requirement(id="R1", text="Writes hello and a newline.", test_ids=["T1"])],
        constraints=["no libc"],
    )


def _cases() -> list[TestCase]:
    return [
        TestCase(
            id="T1",
            kind=TestKind.IO_GOLDEN,
            level=Level.V6,
            inputs={"stdin": ""},
            expect=Expectation(stdout="hello\n", exit_code=0),
            origin=TestOrigin.TEST_AUTHOR,
        )
    ]


def test_typescript_reference_matches_python_ids_and_reingest_is_empty(tmp_path) -> None:
    if not is_available():
        pytest.skip("npx is not installed; the TypeScript World Model cannot run")
    try:
        ts = TsWorldModel(tmp_path / "ts-store")
    except TsWorldModelUnavailable as exc:
        pytest.skip(f"the TypeScript World Model is unavailable: {exc}")

    entities = record_spec_and_tests("r1", _spec(), _cases(), "m1", "m2")
    python_ids = {entity.id for entity in entities}
    try:
        assert all(ts.upsert(entity) for entity in entities)  # first ingest writes
        assert not any(ts.upsert(entity) for entity in entities)  # re-ingest: empty diff
        listed = ts.entities(run_id="r1")
        assert {entity["id"] for entity in listed} == python_ids
    finally:
        ts.close()
