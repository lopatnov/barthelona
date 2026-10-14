"""Repository over `var/app.sqlite`: runs, commands, events, gates and the LLM-call ledger (§17, §18).

Rows keep a few indexed columns plus the full domain document as JSON. Every read validates the document
back into its domain model, so a row that no longer matches the schema fails loudly instead of leaking
into the engine or the UI.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

import orjson

from barthelona.domain import (
    GateDecision,
    GateRequest,
    LLMCallRecord,
    Run,
    RunCommand,
    RunEvent,
    RunStatus,
    StopReason,
)

# Events and gate requests carry references, not bulk data; anything larger belongs in `payload_ref`.
MAX_PAYLOAD_BYTES = 16_384
DEFAULT_PAGE = 500

Clock = Callable[[], datetime]


class NotFoundError(LookupError):
    """The requested row does not exist."""


class ConflictError(RuntimeError):
    """The write contradicts the stored state (a duplicate id, a gap in event numbers, a resolved gate)."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    """All reads and writes of the app database. Writers hold `BEGIN IMMEDIATE` for each operation."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock = _utc_now) -> None:
        self._conn = conn
        self._clock = clock
        self._write_depth = 0

    def close(self) -> None:
        """Close the underlying connection (usable with `contextlib.closing`)."""
        self._conn.close()

    # --- runs ------------------------------------------------------------------------------------

    def create_run(self, run: Run) -> None:
        now = self._now()
        with self._write():
            try:
                self._conn.execute(
                    "INSERT INTO runs (id, status, stop_reason, created_at, updated_at, doc)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (run.id, run.status, run.stop_reason, now, now, run.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"run {run.id!r} already exists") from exc

    def get_run(self, run_id: str) -> Run:
        row = self._conn.execute("SELECT doc FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"run {run_id!r} not found")
        return Run.model_validate_json(row["doc"])

    def list_runs(self, status: RunStatus | None = None) -> list[Run]:
        if status is None:
            rows = self._conn.execute("SELECT doc FROM runs ORDER BY created_at, id")
        else:
            rows = self._conn.execute(
                "SELECT doc FROM runs WHERE status = ? ORDER BY created_at, id", (status,)
            )
        return [Run.model_validate_json(row["doc"]) for row in rows]

    def set_run_status(self, run_id: str, status: RunStatus, stop_reason: StopReason | None = None) -> Run:
        """Move a run to `status`; the domain model rejects a stop without a reason and vice versa."""
        with self._write():
            run = self.get_run(run_id)
            updated = Run.model_validate(run.model_dump() | {"status": status, "stop_reason": stop_reason})
            self._save_run(updated)
        return updated

    def claim_next_queued_run(self) -> Run | None:
        """Atomically move the oldest queued run to `running` and return it (the worker's claim)."""
        with self._write():
            row = self._conn.execute(
                "SELECT id FROM runs WHERE status = ? ORDER BY created_at, id LIMIT 1", (RunStatus.QUEUED,)
            ).fetchone()
            if row is None:
                return None
            run = self.get_run(row["id"])
            run = Run.model_validate(run.model_dump() | {"status": RunStatus.RUNNING})
            self._save_run(run)
        return run

    def _save_run(self, run: Run) -> None:
        self._conn.execute(
            "UPDATE runs SET status = ?, stop_reason = ?, updated_at = ?, doc = ? WHERE id = ?",
            (run.status, run.stop_reason, self._now(), run.model_dump_json(), run.id),
        )

    # --- events ----------------------------------------------------------------------------------

    def next_seq(self, run_id: str) -> int:
        row = self._conn.execute("SELECT MAX(seq) AS last FROM events WHERE run_id = ?", (run_id,)).fetchone()
        return 0 if row["last"] is None else int(row["last"]) + 1

    def append_events(self, events: Sequence[RunEvent]) -> None:
        """Append one batch for one run. Sequence numbers must continue the log without gaps."""
        if not events:
            return
        run_id = events[0].run_id
        if any(event.run_id != run_id for event in events):
            raise ValueError("a batch of events belongs to one run")
        for event in events:
            _check_payload_size("event", event.payload)
        with self._write():
            expected = self.next_seq(run_id)
            for offset, event in enumerate(events):
                if event.seq != expected + offset:
                    raise ConflictError(
                        f"run {run_id!r}: event seq {event.seq} given, {expected + offset} expected"
                    )
            try:
                self._conn.executemany(
                    "INSERT INTO events (run_id, seq, ts, kind, doc) VALUES (?, ?, ?, ?, ?)",
                    [(e.run_id, e.seq, e.ts.isoformat(), e.kind, e.model_dump_json()) for e in events],
                )
            except sqlite3.IntegrityError as exc:
                raise NotFoundError(f"run {run_id!r} not found") from exc

    def events_after(self, run_id: str, after_seq: int = -1, limit: int = DEFAULT_PAGE) -> list[RunEvent]:
        """Events with `seq > after_seq`, oldest first: what a live page polls for (§17)."""
        rows = self._conn.execute(
            "SELECT doc FROM events WHERE run_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (run_id, after_seq, limit),
        )
        return [RunEvent.model_validate_json(row["doc"]) for row in rows]

    # --- gates -----------------------------------------------------------------------------------

    def open_gate(self, request: GateRequest) -> None:
        _check_payload_size("gate", request.payload)
        with self._write():
            try:
                self._conn.execute(
                    "INSERT INTO gates (gate_id, run_id, kind, created_at, request) VALUES (?, ?, ?, ?, ?)",
                    (request.gate_id, request.run_id, request.kind, self._now(), request.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"gate {request.gate_id!r} exists or its run is unknown") from exc

    def resolve_gate(self, decision: GateDecision) -> None:
        """Record the decision once; it must be one of the options the gate offered."""
        _check_payload_size("gate decision", decision.edits)
        with self._write():
            row = self._conn.execute(
                "SELECT request, resolved_at FROM gates WHERE gate_id = ?", (decision.gate_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"gate {decision.gate_id!r} not found")
            if row["resolved_at"] is not None:
                raise ConflictError(f"gate {decision.gate_id!r} is already resolved")
            request = GateRequest.model_validate_json(row["request"])
            if decision.decision not in request.options:
                raise ValueError(f"decision {decision.decision!r} is not one of {request.options}")
            self._conn.execute(
                "UPDATE gates SET resolved_at = ?, decision = ? WHERE gate_id = ?",
                (self._now(), decision.model_dump_json(), decision.gate_id),
            )

    def _check_gate_run(self, gate_id: str, run_id: str) -> None:
        row = self._conn.execute("SELECT run_id FROM gates WHERE gate_id = ?", (gate_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"gate {gate_id!r} not found")
        if row["run_id"] != run_id:
            raise ValueError(f"gate {gate_id!r} belongs to run {row['run_id']!r}, not {run_id!r}")

    def pending_gates(self, run_id: str) -> list[GateRequest]:
        rows = self._conn.execute(
            "SELECT request FROM gates WHERE run_id = ? AND resolved_at IS NULL ORDER BY created_at, gate_id",
            (run_id,),
        )
        return [GateRequest.model_validate_json(row["request"]) for row in rows]

    # --- commands --------------------------------------------------------------------------------

    def enqueue_command(self, command: RunCommand) -> int:
        """Queue a command for the worker; a resume must name a gate of the same run."""
        if command.decision is not None:
            _check_payload_size("gate decision", command.decision.edits)
        with self._write():
            if command.decision is not None:
                self._check_gate_run(command.decision.gate_id, command.run_id)
            try:
                cursor = self._conn.execute(
                    "INSERT INTO commands (run_id, kind, created_at, doc) VALUES (?, ?, ?, ?)",
                    (command.run_id, command.kind, self._now(), command.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                raise NotFoundError(f"run {command.run_id!r} not found") from exc
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite returned no rowid for the new command")
        return cursor.lastrowid

    def claim_commands(self, run_id: str) -> list[RunCommand]:
        """Return the run's unclaimed commands in order and mark them claimed, so each runs once."""
        with self._write():
            rows = self._conn.execute(
                "SELECT id, doc FROM commands WHERE run_id = ? AND claimed_at IS NULL ORDER BY id", (run_id,)
            ).fetchall()
            self._conn.executemany(
                "UPDATE commands SET claimed_at = ? WHERE id = ?", [(self._now(), row["id"]) for row in rows]
            )
        return [RunCommand.model_validate_json(row["doc"]) for row in rows]

    # --- LLM-call ledger -------------------------------------------------------------------------

    def record_llm_call(self, run_id: str, record: LLMCallRecord) -> None:
        with self._write():
            try:
                self._conn.execute(
                    "INSERT INTO llm_calls"
                    " (run_id, provider, model, tokens_in, tokens_out, usd, created_at, doc)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        record.provider,
                        record.model,
                        record.tokens_in,
                        record.tokens_out,
                        record.usd,
                        self._now(),
                        record.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise NotFoundError(f"run {run_id!r} not found") from exc

    def llm_calls(self, run_id: str) -> list[LLMCallRecord]:
        rows = self._conn.execute("SELECT doc FROM llm_calls WHERE run_id = ? ORDER BY id", (run_id,))
        return [LLMCallRecord.model_validate_json(row["doc"]) for row in rows]

    # --- helpers ---------------------------------------------------------------------------------

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()

    @contextmanager
    def _write(self) -> Iterator[None]:
        """One `BEGIN IMMEDIATE` transaction per operation; nested calls join the outer one."""
        if self._write_depth:
            self._write_depth += 1
            try:
                yield
            finally:
                self._write_depth -= 1
            return
        self._conn.execute("BEGIN IMMEDIATE")
        self._write_depth = 1
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()
        finally:
            self._write_depth = 0


def _check_payload_size(what: str, payload: object) -> None:
    size = len(orjson.dumps(payload))
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"{what} payload is {size} bytes (limit {MAX_PAYLOAD_BYTES}); store bulky data under var/runs "
            "and reference it with payload_ref"
        )
