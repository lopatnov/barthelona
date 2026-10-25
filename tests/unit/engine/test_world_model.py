"""The engine records a run's spec, tests, attempts and stop reason in the World Model (D-058)."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Linker,
    ObjFormat,
    Run,
    RunBudget,
    RunEnv,
    RunMode,
    TargetProfile,
)
from barthelona.domain.layout import REQUEST_FILE
from barthelona.engine.graph import build_graph
from barthelona.engine.host import no_facts, services_for
from barthelona.engine.worker import Worker
from barthelona.llm import FakeGateway
from barthelona.persistence import Store, connect, migrate
from barthelona.world_model import WorldModel

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)

INTAKE = '{"lang": "ru", "goal_en": "Print hello.", "entities": ["stdout"], "assumptions": ["Linux x64"]}'
SPEC = (
    '{"slug": "hello", "summary_en": "Prints hello.",'
    ' "requirements": [{"id": "R1", "text": "Writes hello and a newline to stdout."}],'
    ' "modules": [{"path": "src/hello.asm", "purpose": "entry", "exports": ["_start"]}]}'
)
TESTS = '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdout": "hello\\n", "exit_code": 0}]}'
REPLIES = [INTAKE, SPEC, TESTS]


def _run(run_id: str = "r1") -> Run:
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
    return Run(
        id=run_id,
        mode=RunMode.CREATE,
        workspace="workspaces/demo",
        target=target,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=100_000),
    )


async def test_a_run_records_spec_and_tests_into_the_world_model(tmp_path: Path) -> None:
    conn = connect(tmp_path / "app.sqlite")
    migrate(conn)
    with closing(conn):
        store = Store(conn, clock=lambda: NOW)
        runs = tmp_path / "runs"
        world = WorldModel()
        gateway = FakeGateway(REPLIES * 4)
        services = replace(
            services_for(store, runs, lambda _run: gateway, no_facts, world=world),
            preflight=lambda _run_id: None,
        )
        worker = Worker(store, build_graph(services, InMemorySaver()), clock=lambda: NOW, world=world)

        store.create_run(_run())
        (runs / "r1").mkdir(parents=True, exist_ok=True)
        (runs / "r1" / REQUEST_FILE).write_text("Напиши hello на ассемблере.", encoding="utf-8")
        await worker.step()  # drives to gate G1, after validate_spec has written the spec and tests

        kinds = {entity.kind for entity in world.entities(run_id="r1")}
        assert kinds == {"run", "requirement", "test"}
        assert any("Writes hello" in entity.attrs["text"] for entity in world.entities(kind="requirement"))
