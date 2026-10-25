"""The Python World Model: stable IDs, empty-diff re-ingest, persistence and the record helpers (D-058)."""

from __future__ import annotations

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
from barthelona.world_model import (
    ATTEMPT,
    REQUIREMENT,
    RUN,
    TEST,
    Provenance,
    WorldEntity,
    WorldModel,
    case_key,
    external_id,
    format_entities,
    record_attempt,
    record_run_stop,
    record_spec_and_tests,
)


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


def test_external_ids_are_stable_and_match_the_typescript_hash() -> None:
    # djb2("run:barthelona:a") == 1065168406 == 0x3f7d2e16, the same hash the TypeScript `externalId` uses.
    assert external_id("run", "barthelona", "a") == "ext_3f7d2e16"
    assert external_id("run", "barthelona", "r1") != external_id("test", "barthelona", "r1")


def test_upsert_reports_an_empty_diff_on_reingest_and_merges_new_attrs() -> None:
    store = WorldModel()
    entity = WorldEntity(TEST, case_key("r1", "T1"), {"run_id": "r1", "stdout": "hello\n"}, Provenance())
    assert store.upsert(entity) is True
    assert store.upsert(entity) is False  # identical data: empty diff
    merged = WorldEntity(
        entity.kind,
        entity.key,
        {"run_id": "r1", "stdout": "hello\n", "exit_code": 0},
        entity.provenance,
    )
    assert store.upsert(merged) is True  # new attrs: changed
    stored = store.entities(run_id="r1", kind=TEST)[0]
    assert stored.attrs["stdout"] == "hello\n"
    assert stored.attrs["exit_code"] == 0


def test_record_spec_and_tests_builds_one_entity_per_kind() -> None:
    entities = record_spec_and_tests("r1", _spec(), _cases(), "m1", "m2")
    assert {entity.kind for entity in entities} == {RUN, REQUIREMENT, TEST}
    assert len([e for e in entities if e.kind == REQUIREMENT]) == 1
    assert len([e for e in entities if e.kind == TEST]) == 1
    # The same data always yields the same stable ids.
    again = record_spec_and_tests("r1", _spec(), _cases(), "m1", "m2")
    assert [e.id for e in entities] == [e.id for e in again]


def test_record_run_stop_merges_over_the_run_entity() -> None:
    store = WorldModel()
    store.upsert_all(record_spec_and_tests("r1", _spec(), _cases(), "m1", "m2"))
    store.upsert(record_run_stop("r1", "green"))
    run = store.entities(run_id="r1", kind=RUN)[0]
    assert run.attrs["stop_reason"] == "green"
    assert run.attrs["slug"] == "hello"  # the earlier attrs survive the merge


def test_record_attempt_carries_verdict_and_provenance() -> None:
    entity = record_attempt("r1", "hello", 2, "pass", ("test T1: ok",), 3, "qwen", "planner")
    assert entity.kind == ATTEMPT
    assert entity.attrs["verdict"] == "pass"
    assert entity.attrs["chunks"] == 3
    assert entity.provenance.by == "qwen"
    assert entity.provenance.route == "planner"


def test_entities_filter_by_run_kind_and_slug_for_recall() -> None:
    store = WorldModel()
    store.upsert_all(record_spec_and_tests("r1", _spec(), _cases(), "m", "m"))
    store.upsert_all(record_spec_and_tests("r2", _spec(), _cases(), "m", "m"))
    prior = [entity for entity in store.entities(slug="hello") if entity.run_id != "r2"]
    assert {entity.run_id for entity in prior} == {"r1"}
    assert {entity.run_id for entity in store.entities(run_id="r2")} == {"r2"}


def test_file_round_trip_preserves_entities(tmp_path) -> None:
    path = tmp_path / "wm.json"
    writer = WorldModel(path)
    writer.upsert(
        WorldEntity(
            TEST,
            case_key("r1", "T1"),
            {"run_id": "r1", "slug": "hello", "stdout": "hello\n"},
            Provenance(by="m", route="worker", run_id="r1"),
        )
    )
    writer.close()

    reader = WorldModel(path)
    assert reader.count() == 1
    entity = reader.entities(run_id="r1")[0]
    assert entity.attrs["stdout"] == "hello\n"
    assert entity.provenance.route == "worker"


def test_format_entities_names_kind_key_and_provenance() -> None:
    entity = record_attempt("r1", "hello", 1, "fail", ("bad"), 2, "qwen", "worker")
    line = format_entities([entity])
    assert "attempt" in line
    assert "r1:attempt:1" in line
    assert "verdict='fail'" in line
    assert "model qwen" in line
