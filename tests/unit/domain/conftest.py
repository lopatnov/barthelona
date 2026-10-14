"""Valid sample documents for the domain-model tests; each test mutates one thing and expects a rejection."""

from __future__ import annotations

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    BacklogItem,
    ContractRegistry,
    Dialect,
    EdgeSpec,
    Level,
    Linker,
    LoopBound,
    ModuleSpec,
    NodeSpec,
    ObjFormat,
    Outcome,
    ProjectSpec,
    RegisterContract,
    Requirement,
    Role,
    Run,
    RunBudget,
    RunEnv,
    RunMode,
    SprintBudget,
    SprintPlan,
    StoryKind,
    Symbol,
    SymbolKind,
    TargetProfile,
    Task,
    TaskPipeline,
)


@pytest.fixture
def target() -> TargetProfile:
    return TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=Dialect.NASM,
        dialect_version="3.02",
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
        dod={StoryKind.CREATE_MODULE: Level.V5, StoryKind.INTEGRATION: Level.V6},
    )


@pytest.fixture
def project(target: TargetProfile) -> ProjectSpec:
    return ProjectSpec(
        id="p1",
        slug="strlen-demo",
        request_original="Напиши strlen и программу, которая печатает длину аргумента",
        request_lang="ru",
        summary_en="A strlen library function and a program that prints the length of argv[1].",
        target=target,
        requirements=[Requirement(id="R1", text="strlen returns the byte count", test_ids=["T1"])],
        modules=[
            ModuleSpec(path="src/strlen.asm", purpose="strlen", exports=["bart_strlen"]),
            ModuleSpec(path="src/main.asm", purpose="entry point", imports=["bart_strlen"]),
        ],
    )


@pytest.fixture
def registry(target: TargetProfile) -> ContractRegistry:
    strlen = Symbol(
        name="bart_strlen",
        kind=SymbolKind.FUNC,
        module="src/strlen.asm",
        inputs=[RegisterContract(reg="rdi", type="char*", desc="NUL-terminated string")],
        outputs=[RegisterContract(reg="rax", type="u64")],
        clobbers=["rcx"],
    )
    return ContractRegistry(version=1, target=target, symbols={"bart_strlen": strlen}, frozen=["bart_strlen"])


@pytest.fixture
def pipeline() -> TaskPipeline:
    """The `module_create` example of docs/architecture.md §9.2, expanded with default knobs."""
    nodes = [
        NodeSpec(id="ctx", type="context_build", params={"profile": "16k"}),
        NodeSpec(id="code", type="codegen", role=Role.WORKER),
        NodeSpec(id="apply", type="apply_patch"),
        NodeSpec(id="tamper", type="tamper_gate"),
        NodeSpec(id="ladder", type="ladder", params={"up_to": "dod"}),
        NodeSpec(id="triage", type="triage"),
        NodeSpec(id="fix", type="fixer", role=Role.WORKER),
        NodeSpec(id="ok", type="exit_ok"),
        NodeSpec(id="esc", type="exit_escalate"),
    ]
    edges = [
        ("ctx", "code", Outcome.ALWAYS),
        ("code", "apply", Outcome.OK),
        ("code", "esc", Outcome.FAIL),
        ("apply", "tamper", Outcome.OK),
        ("apply", "triage", Outcome.FAIL),
        ("tamper", "ladder", Outcome.OK),
        ("tamper", "triage", Outcome.FAIL),
        ("ladder", "ok", Outcome.OK),
        ("ladder", "triage", Outcome.FAIL),
        ("triage", "fix", Outcome.ALWAYS),
        ("fix", "apply", Outcome.OK),
        ("fix", "esc", Outcome.FAIL),
    ]
    return TaskPipeline(
        nodes=nodes,
        edges=[EdgeSpec(src=s, dst=d, when=w) for s, d, w in edges],
        loops=[LoopBound(back_edge=("fix", "apply"), max_iters=3, on_exhaust="esc")],
        entry="ctx",
        exits_ok=["ok"],
        exits_fail=["esc"],
        max_llm_calls=4,
    )


@pytest.fixture
def item() -> BacklogItem:
    return BacklogItem(
        id="S1", kind=StoryKind.CREATE_MODULE, title="strlen module", modules=["src/strlen.asm"]
    )


@pytest.fixture
def plan() -> SprintPlan:
    return SprintPlan(
        sprint_no=1,
        goal="strlen and main",
        item_ids=["S1", "S2"],
        tasks=[
            Task(id="t_strlen", item_id="S1", module="src/strlen.asm", write_scope=["src/strlen.asm"]),
            Task(
                id="t_main",
                item_id="S2",
                module="src/main.asm",
                depends_on=["t_strlen"],
                write_scope=["src/main.asm"],
            ),
        ],
        layers=[["t_strlen"], ["t_main"]],
        budget=SprintBudget(max_llm_calls=20),
    )


@pytest.fixture
def run(target: TargetProfile) -> Run:
    return Run(
        id="r1",
        mode=RunMode.CREATE,
        workspace="workspaces/strlen-demo",
        target=target,
        policy_version="v1",
        budget=RunBudget(wall_s=4 * 3600, tokens=2_000_000),
    )
