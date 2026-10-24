"""The worker and the outer run graph: claim, park at gate G1, resume, cancel, stops, crash recovery."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    CommandKind,
    Dialect,
    EventKind,
    GateDecision,
    Linker,
    ObjFormat,
    Run,
    RunBudget,
    RunCommand,
    RunEnv,
    RunMode,
    RunStatus,
    StopReason,
    TargetProfile,
)
from barthelona.engine.graph import build_graph
from barthelona.engine.worker import Worker
from barthelona.persistence import Store, connect, migrate

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


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


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    conn = connect(tmp_path / "app.sqlite")
    migrate(conn)
    with closing(conn):
        yield Store(conn, clock=lambda: NOW)


def _worker(store: Store, reason: str | None = None, saver: object | None = None) -> Worker:
    graph = build_graph(lambda _run_id: reason, saver or InMemorySaver())  # type: ignore[arg-type]
    return Worker(store, graph, clock=lambda: NOW)


def _decide(store: Store, decision: str, run_id: str = "r1") -> None:
    gate = store.pending_gates(run_id)[0]
    answer = GateDecision(gate_id=gate.gate_id, decision=decision, at=NOW)
    store.enqueue_command(RunCommand(run_id=run_id, kind=CommandKind.RESUME, decision=answer))


def _kinds(store: Store, run_id: str = "r1") -> list[EventKind]:
    return [event.kind for event in store.events_after(run_id)]


async def test_a_queued_run_stops_at_gate_g1_with_the_gate_open(store: Store) -> None:
    store.create_run(_run())
    worker = _worker(store)
    assert await worker.step() is True
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    [gate] = store.pending_gates("r1")
    assert (gate.gate_id, gate.kind.value, gate.options) == ("r1-G1", "G1", ["approve", "reject"])
    assert _kinds(store) == [EventKind.NODE_END, EventKind.GATE_REQUESTED]
    assert await worker.step() is False  # nothing to do until the UI answers


async def test_rejecting_the_gate_stops_the_run_as_a_human_abort(store: Store) -> None:
    store.create_run(_run())
    worker = _worker(store)
    await worker.step()
    _decide(store, "reject")
    assert await worker.step() is True
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.HUMAN_ABORT)
    assert store.pending_gates("r1") == []
    assert _kinds(store)[-4:] == [
        EventKind.GATE_RESOLVED,
        EventKind.NODE_END,
        EventKind.NODE_END,
        EventKind.STOP,
    ]


async def test_approving_stops_with_an_infra_error_until_the_rest_of_the_flow_exists(store: Store) -> None:
    store.create_run(_run())
    worker = _worker(store)
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.INFRA_ERROR)
    errors = [e for e in store.events_after("r1") if e.kind is EventKind.ERROR]
    assert "not built yet" in errors[0].payload["error"]


async def test_an_unsupported_target_stops_before_any_gate(store: Store) -> None:
    store.create_run(_run())
    worker = _worker(store, reason="no nasm in the image")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.UNSUPPORTED_TARGET)
    assert store.pending_gates("r1") == []


async def test_cancelling_a_waiting_run_stops_it(store: Store) -> None:
    store.create_run(_run())
    worker = _worker(store)
    await worker.step()
    store.enqueue_command(RunCommand(run_id="r1", kind=CommandKind.CANCEL))
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.HUMAN_ABORT)


async def test_two_runs_wait_independently(store: Store) -> None:
    store.create_run(_run("r1"))
    store.create_run(_run("r2"))
    worker = _worker(store)
    await worker.step()
    await worker.step()
    assert [r.status for r in store.list_runs()] == [RunStatus.WAITING_GATE] * 2
    _decide(store, "reject", "r2")
    await worker.step()
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    assert store.get_run("r2").stop_reason is StopReason.HUMAN_ABORT


@pytest.fixture
async def sqlite_saver(tmp_path: Path) -> AsyncIterator[AsyncSqliteSaver]:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite")) as saver:
        yield saver


async def test_a_crashed_worker_continues_from_its_checkpoint_without_a_second_gate(
    store: Store, sqlite_saver: AsyncSqliteSaver
) -> None:
    store.create_run(_run())
    await _worker(store, saver=sqlite_saver).step()
    store.set_run_status(
        "r1", RunStatus.RUNNING
    )  # the crash came after the interrupt, before the status write
    assert await _worker(store, saver=sqlite_saver).recover() == 1
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    assert len(store.pending_gates("r1")) == 1
    _decide(store, "reject")
    await _worker(store, saver=sqlite_saver).step()
    assert store.get_run("r1").stop_reason is StopReason.HUMAN_ABORT


def test_preflight_accepts_the_phase_1_presets_and_names_any_other(store: Store) -> None:
    from barthelona.engine.preflight import SUPPORTED_PRESETS, preflight_for

    store.create_run(_run("r1"))
    other = _run("r2")
    other = Run.model_validate(
        other.model_dump() | {"target": other.target.model_dump() | {"preset": "win-x64-masm"}}
    )
    store.create_run(other)
    check = preflight_for(store)
    assert "linux-x64-nasm-static" in SUPPORTED_PRESETS
    assert check("r1") is None
    assert "win-x64-masm" in (check("r2") or "")


def test_the_worker_command_runs_what_is_queued_and_exits(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from barthelona.cli import app
    from barthelona.persistence import open_store

    db = tmp_path / "app.sqlite"
    with closing(open_store(db)) as seed:
        seed.create_run(_run())
    result = CliRunner().invoke(
        app, ["worker", "--once", "--db", str(db), "--checkpoints", str(tmp_path / "cp.sqlite")]
    )
    assert result.exit_code == 0, result.output
    with closing(open_store(db)) as check:
        assert check.get_run("r1").status is RunStatus.WAITING_GATE
        assert [g.gate_id for g in check.pending_gates("r1")] == ["r1-G1"]
