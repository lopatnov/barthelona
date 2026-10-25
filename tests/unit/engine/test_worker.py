"""The worker and the outer run graph: claim, park at gate G1, resume, cancel, stops, crash recovery."""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator, Callable, Iterator
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
from barthelona.domain.layout import REQUEST_FILE, SPEC_FILE, TESTS_FILE
from barthelona.engine.graph import build_graph
from barthelona.engine.host import default_facts, no_facts, services_for
from barthelona.engine.worker import Worker
from barthelona.llm import FakeGateway, GatewayError
from barthelona.llm.markovian import COMPLETE
from barthelona.llm.types import Completion, CompletionRequest
from barthelona.llm.zetaris import ZetarisError
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
    facts: Callable[[], str] = no_facts,
    gateway: FakeGateway | None = None,
) -> Worker:
    gateway = gateway or FakeGateway(REPLIES * 4 if replies is None else replies)
    services = services_for(store, runs_dir, lambda _run: gateway, facts)
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


needs_nasm = pytest.mark.skipif(
    shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it"
)
_HELLO = (
    '```asm\nsection .data\nmsg db "hello", 10\nlen equ $ - msg\nsection .text\nglobal _start\n_start:\n'
    "    mov rax, 1\n    mov rdi, 1\n    mov rsi, msg\n    mov rdx, len\n    syscall\n"
    f"    mov rax, 60\n    xor rdi, rdi\n    syscall\n```\n{COMPLETE}"
)


@needs_nasm
async def test_approving_g1_writes_the_source_and_parks_at_g4_then_the_run_is_green(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir, replies=[*REPLIES, _HELLO])
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    [gate] = store.pending_gates("r1")
    assert (gate.gate_id, gate.kind.value, gate.payload) == (
        "r1-G4",
        "G4",
        {"source_file": "main.asm", "verdict": "pass"},
    )
    assert "mov rax, 60" in (runs_dir / "r1" / "main.asm").read_text(encoding="utf-8")
    _decide(store, "approve")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.GREEN)


@needs_nasm
async def test_rejecting_g4_stops_the_run_as_a_human_abort(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir, replies=[*REPLIES, _HELLO])
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    _decide(store, "reject")
    await worker.step()
    assert store.get_run("r1").stop_reason is StopReason.HUMAN_ABORT


@needs_nasm
async def test_a_program_the_oracle_rejects_never_reaches_g4(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    worker = _worker(
        store,
        runs_dir,
        replies=[*REPLIES, _HELLO.replace("hello", "howdy")] + [_HELLO.replace("hello", "howdy")] * 5,
    )
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.MAX_ATTEMPTS)
    assert store.pending_gates("r1") == []
    assert not (runs_dir / "r1" / "main.asm").exists()


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


async def test_knowledge_store_facts_reach_the_spec_and_test_prompts_but_not_intake(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)
    gateway = FakeGateway(REPLIES)
    await _worker(store, runs_dir, facts=lambda: "SYSCALL write=1", gateway=gateway).step()
    prompts = [call[1].messages[-1].content for call in gateway.calls]
    assert ["SYSCALL write=1" in prompt for prompt in prompts] == [False, True, True]


async def test_a_failing_knowledge_store_stops_the_run_as_an_infra_error(
    store: Store, runs_dir: Path
) -> None:
    _queue(store, runs_dir)

    def down() -> str:
        raise ZetarisError("connection refused")

    await _worker(store, runs_dir, facts=down).step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.INFRA_ERROR)
    errors = [e for e in store.events_after("r1") if e.kind is EventKind.ERROR]
    assert "connection refused" in errors[0].payload["error"]


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


def test_default_facts_is_empty_without_a_key_and_swallows_a_down_zetaris(monkeypatch):
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    assert default_facts()() == ""
    monkeypatch.setenv("ZETARIS_API_KEY", "k")
    monkeypatch.setenv("ZETARIS_REST_URL", "http://127.0.0.1:9")
    assert default_facts()() == ""


class _StallsAtCodegen(FakeGateway):
    """Answers intake, spec and tests, then never answers the codegen call."""

    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        if len(self.calls) >= len(REPLIES):
            await asyncio.sleep(30)
        return await super().complete(role, request)


async def test_a_codegen_that_outlasts_the_run_budget_stops_as_budget_time(
    store: Store, runs_dir: Path
) -> None:
    short = _run().model_copy(update={"budget": RunBudget(wall_s=0.5, tokens=100_000)})
    store.create_run(short)
    (runs_dir / "r1").mkdir(parents=True, exist_ok=True)
    (runs_dir / "r1" / REQUEST_FILE).write_text("Print hello.", encoding="utf-8")
    worker = _worker(store, runs_dir, gateway=_StallsAtCodegen(REPLIES))
    await worker.step()
    _decide(store, "approve")
    await worker.step()
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.BUDGET_TIME)
    assert store.pending_gates("r1") == []


class _SlowIntakeThenStalls(_StallsAtCodegen):
    """The first call (intake) takes 0.7 s; codegen never answers."""

    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        if not self.calls:
            await asyncio.sleep(0.7)
        return await super().complete(role, request)


async def test_time_used_by_earlier_nodes_shortens_the_codegen_allowance(
    store: Store, runs_dir: Path
) -> None:
    run = _run().model_copy(update={"budget": RunBudget(wall_s=1.0, tokens=100_000)})
    store.create_run(run)
    (runs_dir / "r1").mkdir(parents=True, exist_ok=True)
    (runs_dir / "r1" / REQUEST_FILE).write_text("Print hello.", encoding="utf-8")
    worker = _worker(store, runs_dir, gateway=_SlowIntakeThenStalls(REPLIES))
    await worker.step()
    _decide(store, "approve")
    started = time.monotonic()
    await worker.step()
    assert time.monotonic() - started < 0.7  # a fresh 1.0 s allowance would have lasted about 1.0 s
    assert store.get_run("r1").stop_reason == StopReason.BUDGET_TIME


class _NeverAnswers(FakeGateway):
    """Hangs on every model call, as a slow provider does."""

    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        await asyncio.sleep(30)
        return await super().complete(role, request)


async def test_a_cancel_reaches_a_run_that_is_in_the_middle_of_a_model_call(
    store: Store, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("barthelona.engine.worker.CANCEL_POLL_S", 0.05)
    _queue(store, runs_dir)
    worker = _worker(store, runs_dir, gateway=_NeverAnswers(REPLIES))
    driving = asyncio.create_task(worker.step())
    while store.get_run("r1").status is not RunStatus.RUNNING:  # noqa: ASYNC110 - polls the store the worker task writes
        await asyncio.sleep(0.01)
    store.enqueue_command(RunCommand(run_id="r1", kind=CommandKind.CANCEL))
    await asyncio.wait_for(driving, timeout=5)
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.HUMAN_ABORT)


async def test_an_auto_approve_run_answers_g1_itself_and_logs_it(store: Store, runs_dir: Path) -> None:
    short = _run().model_copy(update={"budget": RunBudget(wall_s=0.5, tokens=100_000), "auto_approve": True})
    store.create_run(short)
    (runs_dir / "r1").mkdir(parents=True, exist_ok=True)
    (runs_dir / "r1" / REQUEST_FILE).write_text("Print hello.", encoding="utf-8")
    worker = _worker(store, runs_dir, gateway=_StallsAtCodegen(REPLIES))
    await worker.step()  # no human answers: the run passes G1 and reaches the code step on its own
    run = store.get_run("r1")
    assert (run.status, run.stop_reason) == (RunStatus.STOPPED, StopReason.BUDGET_TIME)
    resolved = [e for e in store.events_after("r1") if e.kind is EventKind.GATE_RESOLVED]
    assert [e.payload for e in resolved] == [{"gate_id": "r1-G1", "decision": "approve", "automatic": True}]


async def test_node_end_events_say_what_the_node_produced(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir).step()
    ended = {e.node_id: e.payload for e in store.events_after("r1") if e.kind is EventKind.NODE_END}
    assert ended["spec"] == {"requirements": 1}
    assert ended["test_author"] == {"requirements": 1, "tests": 1}


async def test_the_g1_gate_carries_the_spec_and_the_tests_for_the_human(store: Store, runs_dir: Path) -> None:
    _queue(store, runs_dir)
    await _worker(store, runs_dir).step()
    [gate] = store.pending_gates("r1")
    assert gate.payload["project_spec"]["summary_en"] == "Prints hello."
    assert [test["id"] for test in gate.payload["tests"]] == ["T1"]


def _green_worker(
    store: Store, runs_dir: Path, packager: Callable[[str], list[str]] | None, *, auto_package: bool = True
) -> Worker:
    store.create_run(_run().model_copy(update={"auto_package": auto_package}))
    graph = build_graph(
        replace(services_for(store, runs_dir, lambda _run: FakeGateway([])), preflight=lambda _id: None)
    )
    return Worker(store, graph, clock=lambda: NOW, packager=packager)


def _events(store: Store) -> list[tuple[EventKind, dict[str, object]]]:
    return [(event.kind, event.payload) for event in store.events_after("r1")]


def test_a_green_run_that_asked_for_it_is_packaged_and_the_event_says_so(
    store: Store, runs_dir: Path
) -> None:
    packaged: list[str] = []

    def packager(run_id: str) -> list[str]:
        packaged.append(run_id)
        return ["a", "b"]

    _green_worker(store, runs_dir, packager)._stop("r1", StopReason.GREEN)

    assert packaged == ["r1"]
    assert _events(store)[-1] == (EventKind.PHASE, {"packaged": "workspaces/demo", "files": 2})


@pytest.mark.parametrize("reason", [StopReason.HUMAN_ABORT, StopReason.MAX_ATTEMPTS])
def test_a_run_that_did_not_stop_green_is_not_packaged(
    store: Store, runs_dir: Path, reason: StopReason
) -> None:
    worker = _green_worker(store, runs_dir, lambda _id: pytest.fail("must not package"))
    worker._stop("r1", reason)


def test_a_run_that_did_not_ask_for_packaging_is_not_packaged(store: Store, runs_dir: Path) -> None:
    worker = _green_worker(store, runs_dir, lambda _id: pytest.fail("must not package"), auto_package=False)
    worker._stop("r1", StopReason.GREEN)
    assert store.get_run("r1").stop_reason is StopReason.GREEN


def test_a_packaging_failure_is_an_event_and_the_run_stays_green(store: Store, runs_dir: Path) -> None:
    def packager(run_id: str) -> list[str]:
        raise ValueError("target folder is not empty")

    _green_worker(store, runs_dir, packager)._stop("r1", StopReason.GREEN)

    kind, payload = _events(store)[-1]
    assert kind is EventKind.ERROR and "not empty" in str(payload["message"])
    assert store.get_run("r1").stop_reason is StopReason.GREEN
