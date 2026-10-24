"""The worker and the outer run graph: claim, park at gate G1, resume, cancel, stops, crash recovery."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import orjson
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
    ProjectSpec,
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
from barthelona.engine.host import REQUEST_FILE, SPEC_FILE, TESTS_FILE, services_for
from barthelona.engine.worker import Worker
from barthelona.llm import FakeGateway, GatewayError
from barthelona.persistence import Store, connect, migrate

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

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


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    conn = connect(tmp_path / "app.sqlite")
    migrate(conn)
    with closing(conn):
        yield Store(conn, clock=lambda: NOW)


def _queue(store: Store, runs_dir: Path, run_id: str = "r1") -> None:
    store.create_run(_run(run_id))
    (runs_dir / run_id).mkdir(parents=True, exist_ok=True)
    (runs_dir / run_id / REQUEST_FILE).write_text("Напиши hello на ассемблере.", encoding="utf-8")


def _read_spec(runs_dir: Path, run_id: str = "r1") -> ProjectSpec:
    return ProjectSpec.model_validate_json((runs_dir / run_id / SPEC_FILE).read_text(encoding="utf-8"))


def _worker(
    store: Store,
    runs_dir: Path,
    reason: str | None = None,
    saver: object | None = None,
    replies: list[str | Exception] | None = None,
) -> Worker:
    gateway = FakeGateway(REPLIES * 4 if replies is None else replies)
    services = services_for(store, runs_dir, lambda _run: gateway)
    services = replace(services, preflight=lambda _run_id: reason)
    graph = build_graph(services, saver or InMemorySaver())  # type: ignore[arg-type]
    return Worker(store, graph, clock=lambda: NOW)


def _decide(store: Store, decision: str, run_id: str = "r1") -> None:
    gate = store.pending_gates(run_id)[0]
    answer = GateDecision(gate_id=gate.gate_id, decision=decision, at=NOW)
    store.enqueue_command(RunCommand(run_id=run_id, kind=CommandKind.RESUME, decision=answer))


def _kinds(store: Store, run_id: str = "r1") -> list[EventKind]:
    return [event.kind for event in store.events_after(run_id)]


async def test_a_queued_run_stops_at_gate_g1_with_the_gate_open(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir)
    assert await worker.step() is True
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    [gate] = store.pending_gates("r1")
    assert (gate.gate_id, gate.kind.value, gate.options) == ("r1-G1", "G1", ["approve", "reject"])
    assert _kinds(store) == [EventKind.NODE_END] * 5 + [EventKind.GATE_REQUESTED]
    assert await worker.step() is False  # nothing to do until the UI answers


async def test_rejecting_the_gate_stops_the_run_as_a_human_abort(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir)
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


async def test_approving_stops_with_an_infra_error_until_the_rest_of_the_flow_exists(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir)
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.INFRA_ERROR)
    errors = [e for e in store.events_after("r1") if e.kind is EventKind.ERROR]
    assert "not built yet" in errors[0].payload["error"]


async def test_the_spec_is_written_for_the_gate_and_every_model_call_is_in_the_ledger(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir).step()
    spec = _read_spec(runs_dir)
    assert (spec.slug, spec.request_lang, spec.target.preset) == ("hello", "ru", "linux-x64-nasm-static")
    assert spec.request_original.startswith("Напиши hello")
    assert spec.assumptions == ["Linux x64"]
    assert [call.tokens_out for call in store.llm_calls("r1")] == [len(r.split()) for r in REPLIES]
    assert spec.requirements[0].test_ids == ["T1"]
    tests = orjson.loads((runs_dir / "r1" / TESTS_FILE).read_bytes())
    assert [(t["id"], t["kind"], t["expect"]["stdout"]) for t in tests] == [("T1", "io_golden", "hello\n")]


async def test_a_reply_that_is_not_json_is_sent_back_once(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    replies: list[str | Exception] = ["I cannot say.", f"```json\n{INTAKE}\n```", SPEC, TESTS]
    await _worker(store, runs_dir, replies=replies).step()
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    assert len(store.llm_calls("r1")) == 4


async def test_two_unusable_replies_stop_the_run_as_max_attempts(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir, replies=["no", '{"lang": "english"}']).step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.MAX_ATTEMPTS)
    assert store.pending_gates("r1") == []


async def test_tests_that_leave_a_requirement_uncovered_are_sent_back(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    uncovered = TESTS.replace('"R1"', '"R9"')
    await _worker(store, runs_dir, replies=[INTAKE, SPEC, uncovered, TESTS]).step()
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    assert len(store.llm_calls("r1")) == 4


async def test_two_test_drafts_that_miss_a_requirement_stop_the_run(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    uncovered = TESTS.replace('"R1"', '"R9"')
    await _worker(store, runs_dir, replies=[INTAKE, SPEC, uncovered, uncovered]).step()
    assert store.get_run("r1").stop_reason is StopReason.MAX_ATTEMPTS
    assert not (runs_dir / "r1" / SPEC_FILE).exists()


async def test_a_chain_with_no_usable_model_stops_the_run_as_no_model_available(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir, replies=[GatewayError("every model failed")]).step()
    assert store.get_run("r1").stop_reason is StopReason.NO_MODEL_AVAILABLE


async def test_an_unsupported_target_stops_before_any_gate(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir, reason="no nasm in the image")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.UNSUPPORTED_TARGET)
    assert store.pending_gates("r1") == []


async def test_cancelling_a_waiting_run_stops_it(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir)
    await worker.step()
    store.enqueue_command(RunCommand(run_id="r1", kind=CommandKind.CANCEL))
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.HUMAN_ABORT)


async def test_two_runs_wait_independently(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir, "r1")
    _queue(store, runs_dir, "r2")
    worker = _worker(store, runs_dir)
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
    store: Store, runs_dir: Path, sqlite_saver: AsyncSqliteSaver
) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir, saver=sqlite_saver).step()
    store.set_run_status(
        "r1", RunStatus.RUNNING
    )  # the crash came after the interrupt, before the status write
    assert await _worker(store, runs_dir, saver=sqlite_saver).recover() == 1
    assert store.get_run("r1").status is RunStatus.WAITING_GATE
    assert len(store.pending_gates("r1")) == 1
    _decide(store, "reject")
    await _worker(store, runs_dir, saver=sqlite_saver).step()
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
        seed.create_run(_run())  # no request file: the run fails before any model is called
    result = CliRunner().invoke(
        app,
        [
            "worker",
            "--once",
            "--db",
            str(db),
            "--checkpoints",
            str(tmp_path / "cp.sqlite"),
            "--runs",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 0, result.output
    with closing(open_store(db)) as check:
        run = check.get_run("r1")
        assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.INFRA_ERROR)
        errors = [e for e in check.events_after("r1") if e.kind is EventKind.ERROR]
        assert "FileNotFoundError" in errors[0].payload["error"]
