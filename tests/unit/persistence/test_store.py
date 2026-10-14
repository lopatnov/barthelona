"""SQLite persistence (docs/architecture.md §17, §18): connections, migrations and the store."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    CommandKind,
    Dialect,
    EventKind,
    GateDecision,
    GateKind,
    GateRequest,
    Linker,
    LLMCallRecord,
    ObjFormat,
    Run,
    RunBudget,
    RunCommand,
    RunEnv,
    RunEvent,
    RunMode,
    RunStatus,
    StopReason,
    TargetProfile,
)
from barthelona.persistence import (
    LATEST_VERSION,
    MAX_PAYLOAD_BYTES,
    ConflictError,
    NotFoundError,
    Store,
    connect,
    connect_readonly,
    migrate,
    migrations,
    open_store,
    schema_version,
)

T0 = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
SHA = "0" * 64


class _Clock:
    """Each call is one second later, so ordering by time is deterministic."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


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


def _event(seq: int, run_id: str = "r1", **payload: object) -> RunEvent:
    return RunEvent(run_id=run_id, seq=seq, ts=T0, kind=EventKind.PHASE, payload=dict(payload))


def _gate(gate_id: str = "g1") -> GateRequest:
    return GateRequest(gate_id=gate_id, kind=GateKind.G1_SPEC, run_id="r1", options=["approve", "edit"])


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "var" / "app.sqlite"


Opener = Callable[[Callable[[Path], sqlite3.Connection]], sqlite3.Connection]


@pytest.fixture
def opened(db_path: Path) -> Iterator[Opener]:
    """Open connections to `db_path` with the given factory and close them all after the test."""
    with ExitStack() as stack:
        yield lambda factory: stack.enter_context(closing(factory(db_path)))


@pytest.fixture
def store(opened: Opener) -> Store:
    conn = opened(connect)
    migrate(conn)
    s = Store(conn, clock=_Clock())
    s.create_run(_run())
    return s


# --- connections and migrations ----------------------------------------------------------------


def test_connect_creates_the_file_in_wal_mode_with_foreign_keys(db_path: Path, opened: Opener) -> None:
    conn = opened(connect)
    assert db_path.is_file()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_is_idempotent_and_versioned(opened: Opener) -> None:
    conn = opened(connect)
    assert schema_version(conn) == 0
    assert migrate(conn) == LATEST_VERSION
    assert migrate(conn) == LATEST_VERSION
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"runs", "commands", "events", "gates", "llm_calls"} <= tables


def test_migrate_refuses_a_newer_schema(opened: Opener) -> None:
    conn = opened(connect)
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 1}")
    with pytest.raises(RuntimeError, match="newer"):
        migrate(conn)


def test_readonly_connection_reads_committed_rows_and_cannot_write(store: Store, opened: Opener) -> None:
    reader_store = Store(opened(connect_readonly))
    assert reader_store.get_run("r1").id == "r1"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader_store.create_run(_run("r2"))


def test_readonly_connection_needs_an_existing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connect_readonly(tmp_path / "missing.sqlite")


def test_readonly_connection_needs_the_current_schema(db_path: Path, opened: Opener) -> None:
    opened(connect)
    with pytest.raises(RuntimeError, match="schema version 0"):
        connect_readonly(db_path)


def test_failed_migration_leaves_the_schema_untouched(
    opened: Opener, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migrations, "MIGRATIONS", ("CREATE TABLE a (x INTEGER); CREATE TABLE a (y);",))
    monkeypatch.setattr(migrations, "LATEST_VERSION", 1)
    conn = opened(connect)
    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        migrate(conn)
    assert schema_version(conn) == 0
    assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


def test_persistence_imports_no_engine_or_ui_modules() -> None:
    """The worker and the UI meet in persistence (invariant 8), so it loads neither; partial cover for F-1."""
    code = (
        "import sys, barthelona.persistence; "
        "banned = ('langgraph', 'langchain_core', 'streamlit', 'openai', 'anthropic', 'google.genai', "
        "'barthelona.engine', 'barthelona.nodes', 'barthelona.ui', 'barthelona.cli'); "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in banned or m in banned))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_open_store_migrates_and_closes(db_path: Path, opened: Opener) -> None:
    with closing(open_store(db_path)) as store:
        store.create_run(_run())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        store.get_run("r1")
    assert schema_version(opened(connect)) == LATEST_VERSION


def test_reader_sees_writes_while_the_writer_stays_open(store: Store, opened: Opener) -> None:
    reader = Store(opened(connect_readonly))
    store.append_events([_event(0)])
    assert [e.seq for e in reader.events_after("r1")] == [0]


# --- runs --------------------------------------------------------------------------------------


def test_runs_round_trip_and_ids_are_unique(store: Store) -> None:
    assert store.get_run("r1") == _run()
    with pytest.raises(ConflictError, match="already exists"):
        store.create_run(_run())
    with pytest.raises(NotFoundError):
        store.get_run("nope")


def test_claim_takes_the_oldest_queued_run_once(store: Store) -> None:
    store.create_run(_run("r2"))
    first = store.claim_next_queued_run()
    second = store.claim_next_queued_run()
    assert (first and first.id, second and second.id) == ("r1", "r2")
    assert store.claim_next_queued_run() is None
    assert [r.id for r in store.list_runs(RunStatus.RUNNING)] == ["r1", "r2"]


def test_a_stop_needs_a_reason(store: Store) -> None:
    with pytest.raises(ValueError, match="stop_reason"):
        store.set_run_status("r1", RunStatus.STOPPED)
    assert store.get_run("r1").status is RunStatus.QUEUED  # the failed write rolled back
    stopped = store.set_run_status("r1", RunStatus.STOPPED, StopReason.BUDGET_TIME)
    assert store.get_run("r1") == stopped
    assert store.list_runs(RunStatus.STOPPED) == [stopped]


# --- events ------------------------------------------------------------------------------------


def test_events_append_in_order_and_page_by_seq(store: Store) -> None:
    store.append_events([_event(0), _event(1)])
    store.append_events([_event(2)])
    assert store.next_seq("r1") == 3
    assert [e.seq for e in store.events_after("r1", after_seq=0)] == [1, 2]
    assert [e.seq for e in store.events_after("r1", limit=1)] == [0]


@pytest.mark.parametrize("batch", [[1], [0, 2], [0, 0]])
def test_event_seq_has_no_gaps_or_repeats(store: Store, batch: list[int]) -> None:
    with pytest.raises(ConflictError, match="expected"):
        store.append_events([_event(seq) for seq in batch])
    assert store.events_after("r1") == []


def test_event_batch_belongs_to_one_known_run(store: Store) -> None:
    with pytest.raises(ValueError, match="one run"):
        store.append_events([_event(0), _event(1, run_id="r2")])
    with pytest.raises(NotFoundError):
        store.append_events([_event(0, run_id="ghost")])


BULK = {"blob": "x" * MAX_PAYLOAD_BYTES}


def test_bulky_payloads_are_refused(store: Store) -> None:
    bulky_decision = GateDecision(gate_id="g1", decision="edit", edits=BULK, at=T0)
    with pytest.raises(ValueError, match="payload_ref"):
        store.append_events([_event(0, **BULK)])
    with pytest.raises(ValueError, match="payload_ref"):
        store.open_gate(_gate().model_copy(update={"payload": BULK}))
    store.open_gate(_gate())
    with pytest.raises(ValueError, match="payload_ref"):
        store.resolve_gate(bulky_decision)
    with pytest.raises(ValueError, match="payload_ref"):
        store.enqueue_command(RunCommand(run_id="r1", kind=CommandKind.RESUME, decision=bulky_decision))


# --- gates and commands ------------------------------------------------------------------------


def test_gate_resolves_once_with_an_offered_option(store: Store) -> None:
    store.open_gate(_gate())
    assert store.pending_gates("r1") == [_gate()]
    with pytest.raises(ValueError, match="not one of"):
        store.resolve_gate(GateDecision(gate_id="g1", decision="maybe", at=T0))
    store.resolve_gate(GateDecision(gate_id="g1", decision="approve", at=T0))
    assert store.pending_gates("r1") == []
    with pytest.raises(ConflictError, match="already resolved"):
        store.resolve_gate(GateDecision(gate_id="g1", decision="edit", at=T0))
    with pytest.raises(NotFoundError):
        store.resolve_gate(GateDecision(gate_id="g9", decision="approve", at=T0))


def test_gate_ids_are_unique(store: Store) -> None:
    store.open_gate(_gate())
    with pytest.raises(ConflictError):
        store.open_gate(_gate())


def test_commands_are_claimed_once_in_order(store: Store) -> None:
    resume = RunCommand(
        run_id="r1",
        kind=CommandKind.RESUME,
        decision=GateDecision(gate_id="g1", decision="approve", at=T0),
    )
    cancel = RunCommand(run_id="r1", kind=CommandKind.CANCEL)
    first_id = store.enqueue_command(resume)
    assert store.enqueue_command(cancel) == first_id + 1
    assert store.claim_commands("r1") == [resume, cancel]
    assert store.claim_commands("r1") == []
    with pytest.raises(NotFoundError):
        store.enqueue_command(RunCommand(run_id="ghost", kind=CommandKind.CANCEL))


@pytest.mark.parametrize(
    ("kind", "extra"),
    [
        (CommandKind.RESUME, {}),
        (CommandKind.CANCEL, {"task_id": "t1"}),
        (CommandKind.RETRY_TASK, {}),
        (CommandKind.EXTEND_BUDGET, {"task_id": "t1"}),
    ],
)
def test_command_arguments_match_their_kind(kind: CommandKind, extra: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="takes"):
        RunCommand.model_validate({"run_id": "r1", "kind": kind} | extra)


# --- LLM-call ledger ---------------------------------------------------------------------------


def test_llm_calls_are_recorded_per_run(store: Store) -> None:
    record = LLMCallRecord(
        provider="lmstudio",
        model="qwen2.5-coder-7b",
        prompt_hash=SHA,
        tokens_in=100,
        tokens_out=20,
        latency_ms=900,
        stop_reason="end_turn",
    )
    store.record_llm_call("r1", record)
    assert store.llm_calls("r1") == [record]
    with pytest.raises(NotFoundError):
        store.record_llm_call("ghost", record)
