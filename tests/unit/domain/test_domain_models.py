"""Domain models (docs/architecture.md §4, §9): valid documents round-trip, invalid ones are rejected."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from barthelona.domain import (
    DOCUMENTS,
    BacklogItem,
    ContractRegistry,
    Diagnostic,
    DiagnosticLevel,
    Document,
    FileWrite,
    Increment,
    JsonPatchOp,
    Knob,
    Lesson,
    LessonKind,
    LevelResult,
    LoopBudget,
    ModuleSpec,
    Patch,
    ProjectSpec,
    Run,
    RunStatus,
    Severity,
    SprintBudget,
    SprintPlan,
    SprintTopology,
    StopReason,
    StructDef,
    StructField,
    SymbolEdit,
    TaskPipeline,
    TaskTopologyChoice,
    TopologyRequest,
    VerificationReport,
    canonical_json,
    spec_hash,
)
from barthelona.domain._base import RelPath

SHA = "0" * 64
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _round_trip(model: BaseModel) -> None:
    again = type(model).model_validate_json(model.model_dump_json())
    assert again == model


def test_samples_round_trip_through_json(
    project: ProjectSpec, registry: ContractRegistry, plan: SprintPlan, run: Run, item: BacklogItem
) -> None:
    for model in (project, registry, plan, run, item):
        _round_trip(model)
        assert model.model_dump()["schema_version"] == 1


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_every_document_has_a_strict_json_schema(name: str) -> None:
    cls = DOCUMENTS[name]
    schema = cls.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "schema_version" in schema["properties"]
    json.dumps(schema)  # serializable as is


def test_documents_registry_lists_every_document_subclass() -> None:
    def subclasses(cls: type[Document]) -> set[type[Document]]:
        found = set(cls.__subclasses__())
        for sub in list(found):
            found |= subclasses(sub)
        return found

    assert set(DOCUMENTS.values()) == subclasses(Document)


def test_models_are_frozen_and_reject_unknown_keys(item: BacklogItem) -> None:
    with pytest.raises(ValidationError):
        item.title = "changed"  # type: ignore[misc]  # mutation must fail; that is the point of the test
    data = item.model_dump()
    data["surprise"] = 1
    with pytest.raises(ValidationError, match="surprise"):
        BacklogItem.model_validate(data)


def test_unknown_schema_version_is_rejected(item: BacklogItem) -> None:
    data = item.model_dump() | {"schema_version": 2}
    with pytest.raises(ValidationError):
        BacklogItem.model_validate(data)


# --- identifiers and paths ---------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["Ctx", "1ctx", "ctx-1", "", "a" * 33])
def test_node_ids_follow_rule_t2(pipeline: TaskPipeline, bad: str) -> None:
    data = pipeline.model_dump()
    data["nodes"][0]["id"] = bad
    with pytest.raises(ValidationError):
        TaskPipeline.model_validate(data)


@pytest.mark.parametrize(
    "bad", ["/etc/passwd", "../x.asm", "src/../../x", "src\\x.asm", "C:/x.asm", "src//x", "./x", "", "a\nb"]
)
def test_rel_paths_stay_inside_the_workspace(bad: str) -> None:
    with pytest.raises(ValidationError):
        ModuleSpec(path=bad, purpose="x")


class _PathBox(BaseModel):
    path: RelPath


@given(st.text(min_size=1, max_size=80))
def test_accepted_rel_paths_have_no_escaping_segments(raw: str) -> None:
    try:
        path = _PathBox(path=raw).path
    except ValidationError:
        return
    parts = path.split("/")
    assert not path.startswith("/")
    assert "\\" not in path and all(ord(ch) >= 0x20 for ch in path)
    assert all(part not in ("", ".", "..") for part in parts)


# --- project and contracts ---------------------------------------------------------------------


def test_project_rejects_duplicate_module_paths(project: ProjectSpec) -> None:
    data = project.model_dump()
    data["modules"].append(data["modules"][0])
    with pytest.raises(ValidationError, match="duplicate module path"):
        ProjectSpec.model_validate(data)


def test_registry_keys_match_names_and_frozen_symbols_exist(registry: ContractRegistry) -> None:
    data = registry.model_dump()
    data["frozen"] = ["missing"]
    with pytest.raises(ValidationError, match="frozen symbols"):
        ContractRegistry.model_validate(data)
    data = registry.model_dump()
    data["symbols"]["other"] = data["symbols"]["bart_strlen"]
    with pytest.raises(ValidationError, match="does not match"):
        ContractRegistry.model_validate(data)


def test_struct_offsets_are_ascending_and_inside_the_struct() -> None:
    StructDef(
        fields=[StructField(name="a", type="u64", off=0), StructField(name="b", type="u32", off=8)], size=16
    )
    with pytest.raises(ValidationError, match="ascending"):
        StructDef(
            fields=[StructField(name="a", type="u64", off=8), StructField(name="b", type="u64", off=0)],
            size=16,
        )
    with pytest.raises(ValidationError, match="beyond"):
        StructDef(fields=[StructField(name="a", type="u64", off=16)], size=16)


# --- backlog, sprints, topology ----------------------------------------------------------------


def test_item_cannot_depend_on_itself(item: BacklogItem) -> None:
    with pytest.raises(ValidationError, match="itself"):
        BacklogItem.model_validate(item.model_dump() | {"depends_on": ["S1"]})


def test_sprint_layers_cover_every_task_once(plan: SprintPlan) -> None:
    for layers, message in (
        ([["t_strlen"]], "every task"),
        ([["t_strlen", "t_main"], ["t_main"]], "duplicate"),
        ([["t_main"], ["t_strlen"]], "later layer"),
        ([["t_strlen", "t_main"]], "later layer"),
    ):
        with pytest.raises(ValidationError, match=message):
            SprintPlan.model_validate(plan.model_dump() | {"layers": layers})


def test_loop_budget_needs_at_least_one_iteration(pipeline: TaskPipeline) -> None:
    data = pipeline.model_dump()
    data["loops"][0]["max_iters"] = 0
    with pytest.raises(ValidationError):
        TaskPipeline.model_validate(data)


def test_topology_request_is_either_l1_or_l2(pipeline: TaskPipeline) -> None:
    choice = TaskTopologyChoice(
        task_id="t_strlen",
        template_id="module_create",
        knobs={"max_fix_iters": 3},
        loop_budgets={"fix->apply": LoopBudget(max_iters=3, max_usd=0.5)},
    )
    TopologyRequest(tasks=[choice], rationale="defaults")
    TopologyRequest(pipelines={"t_strlen": pipeline})
    with pytest.raises(ValidationError, match="either"):
        TopologyRequest()
    with pytest.raises(ValidationError, match="either"):
        TopologyRequest(tasks=[choice], pipelines={"t_strlen": pipeline})
    with pytest.raises(ValidationError):
        TopologyRequest(tasks=[choice], rationale="x" * 301)


def test_slot_takes_at_most_two_insertions() -> None:
    with pytest.raises(ValidationError, match="at most 2"):
        TaskTopologyChoice(
            task_id="t1", template_id="module_create", insertions={"post_apply": ["a", "b", "c"]}
        )


@pytest.mark.parametrize("key", ["fix-apply", "fix->", "Fix->apply", "fix->apply->ok"])
def test_loop_budget_keys_name_one_back_edge(key: str) -> None:
    with pytest.raises(ValidationError):
        TaskTopologyChoice(
            task_id="t1", template_id="module_create", loop_budgets={key: LoopBudget(max_iters=1)}
        )


def test_spec_hash_is_canonical(pipeline: TaskPipeline) -> None:
    shuffled = TaskPipeline.model_validate(dict(reversed(list(pipeline.model_dump().items()))))
    assert canonical_json(shuffled) == canonical_json(pipeline)
    assert spec_hash(shuffled) == spec_hash(pipeline)
    other = pipeline.model_copy(update={"max_llm_calls": 5})
    assert spec_hash(other) != spec_hash(pipeline)
    stamped = pipeline.model_copy(update={"hash": spec_hash(pipeline)})
    assert spec_hash(stamped) == spec_hash(pipeline)  # filling the hash field does not change the hash


def _topology(pipeline: TaskPipeline, **changes: object) -> SprintTopology:
    key = spec_hash(pipeline)
    data: dict[str, object] = {
        "sprint_no": 1,
        "policy_version": "v1",
        "builder_version": "0.0.1",
        "composition_level": "L0",
        "layers": [["t_strlen"], ["t_main"]],
        "pipelines": {key: pipeline.model_copy(update={"hash": key})},
        "task_pipeline": {"t_strlen": key, "t_main": key},
        "budget": SprintBudget(max_llm_calls=8),
    }
    return SprintTopology.model_validate(data | changes)


def test_sprint_topology_maps_every_task_to_a_known_pipeline(pipeline: TaskPipeline) -> None:
    _round_trip(_topology(pipeline))
    with pytest.raises(ValidationError, match="exactly once"):
        _topology(pipeline, layers=[["t_strlen"]])
    with pytest.raises(ValidationError, match="unknown pipelines"):
        _topology(pipeline, task_pipeline={"t_strlen": spec_hash(pipeline), "t_main": SHA})
    with pytest.raises(ValidationError, match="does not match"):
        _topology(
            pipeline,
            pipelines={SHA: pipeline.model_copy(update={"hash": spec_hash(pipeline)})},
            task_pipeline={"t_strlen": SHA, "t_main": SHA},
        )


def test_loop_budgets_have_absolute_ceilings() -> None:
    with pytest.raises(ValidationError):
        LoopBudget(max_iters=17)


# --- runs, stops, budgets ----------------------------------------------------------------------


def test_every_stopped_run_has_a_stop_reason(run: Run) -> None:
    stopped = Run.model_validate(run.model_dump() | {"status": "stopped", "stop_reason": "green"})
    assert stopped.stop_reason is StopReason.GREEN
    with pytest.raises(ValidationError, match="stop_reason"):
        Run.model_validate(run.model_dump() | {"status": RunStatus.STOPPED})
    with pytest.raises(ValidationError, match="stop_reason"):
        Run.model_validate(run.model_dump() | {"stop_reason": StopReason.REFUSAL})


def test_local_only_run_cannot_allow_cloud(run: Run) -> None:
    data = run.model_dump()
    data["budget"]["cloud_allowed"] = True
    with pytest.raises(ValidationError, match="local-only"):
        Run.model_validate(data)
    Run.model_validate(data | {"profile": "hybrid"})


def test_dollar_budget_is_optional(run: Run) -> None:
    assert run.budget.usd is None


# --- verification, patches, lessons, policy ----------------------------------------------------


def test_increment_carries_a_report() -> None:
    report = VerificationReport(
        levels=[
            LevelResult(
                level="V0",
                status="fail",
                secs=0.1,
                diagnostics=[
                    Diagnostic(
                        tool="nasm",
                        level=DiagnosticLevel.V0,
                        severity=Severity.ERROR,
                        message="parser: instruction expected",
                        file="src/strlen.asm",
                        line=7,
                    )
                ],
            )
        ]
    )
    inc = Increment(
        sprint_no=1,
        branch="bart/r1",
        git_sha="a" * 40,
        tag="r1-s1",
        contracts_version=1,
        report=report,
        artifacts={"build/app": SHA},
    )
    _round_trip(inc)
    with pytest.raises(ValidationError):
        Increment.model_validate(inc.model_dump() | {"branch": "main"})


def test_patch_ops_are_discriminated() -> None:
    patch = Patch.model_validate(
        {
            "ops": [
                {"op": "file", "path": "src/a.asm", "content": "ret\n"},
                {"op": "symbol", "path": "src/a.asm", "symbol": "f", "new_text": "f: ret\n"},
            ]
        }
    )
    assert isinstance(patch.ops[0], FileWrite)
    assert isinstance(patch.ops[1], SymbolEdit)
    with pytest.raises(ValidationError):
        Patch.model_validate({"ops": [{"op": "file", "path": "../a.asm", "content": ""}]})


def _lesson(**changes: object) -> Lesson:
    data: dict[str, object] = {
        "id": "L1",
        "kind": LessonKind.PITFALL,
        "rule": "Align the stack to 16 bytes before every call.",
        "created": NOW,
        "source": "retro",
    }
    return Lesson.model_validate(data | changes)


def test_lesson_rule_is_short_and_web_lessons_cite_a_url() -> None:
    _lesson()
    with pytest.raises(ValidationError, match="40 words"):
        _lesson(rule=" ".join(["word"] * 41))
    with pytest.raises(ValidationError, match="url"):
        _lesson(source="web")
    _lesson(source="web", url="https://www.nasm.us/doc/")


@pytest.mark.parametrize(
    "knob",
    [
        {"type": "int", "min": 1, "max": 4, "default": 5},
        {"type": "int", "default": 1},
        {"type": "int", "min": 0, "max": 1, "default": True},
        {"type": "enum", "values": ["8k", "16k"], "default": "32k"},
        {"type": "bool", "default": "yes"},
    ],
)
def test_knob_defaults_are_within_their_ranges(knob: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Knob.model_validate(knob)


def test_json_patch_op_uses_the_rfc_field_name() -> None:
    op = JsonPatchOp.model_validate({"op": "move", "from": "/a", "path": "/b"})
    assert op.model_dump()["from"] == "/a"


# --- layering ----------------------------------------------------------------------------------


def test_domain_imports_no_io_or_framework_modules() -> None:
    """`domain` holds data and pure validation only (.claude/rules/python.md); partial cover for F-1."""
    code = (
        "import sys, barthelona.domain; "
        "banned = ('langgraph', 'langchain_core', 'streamlit', 'openai', 'anthropic', 'google.genai', "
        "'httpx', 'sqlite3', 'aiosqlite', 'subprocess', 'barthelona.cli'); "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in banned or m in banned))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
