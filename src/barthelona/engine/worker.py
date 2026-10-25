"""The worker: the one process that runs the engine (docs/architecture.md §17).

It claims queued runs, streams the outer run graph, records every node and gate as an event, parks a run at a
human gate and continues it when the UI queues a `resume` command. After a crash it streams `None` on the same
thread, so a run continues from its last checkpoint (D-044). The UI and CLI never run the graph; they write
runs and commands to SQLite (invariant 8).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command

from barthelona.domain import (
    CommandKind,
    EventKind,
    GateDecision,
    GateRequest,
    Run,
    RunCommand,
    RunEvent,
    RunStatus,
    StopReason,
)
from barthelona.engine.gates import node_summary
from barthelona.persistence import Store

log = logging.getLogger(__name__)

Clock = Callable[[], datetime]

CANCEL_POLL_S = 1.0  # how often a run in progress looks for a Cancel the UI has queued
AUTO_APPROVE = "approve"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Worker:
    def __init__(self, store: Store, graph: Any, clock: Clock = _utc_now) -> None:
        self._store = store
        self._graph = graph
        self._clock = clock

    # --- one pass --------------------------------------------------------------------------------

    async def step(self) -> bool:
        """Answer waiting gates, then start one queued run; True when anything happened."""
        progressed = False
        for run in self._store.list_runs(RunStatus.WAITING_GATE):
            progressed = await self._answer_commands(run) or progressed
        queued = self._store.claim_next_queued_run()
        if queued is not None:
            await self._drive(queued.id, {"run_id": queued.id})
            progressed = True
        return progressed

    async def recover(self) -> int:
        """Continue every run that was running when the worker died; returns how many."""
        crashed = self._store.list_runs(RunStatus.RUNNING)
        for run in crashed:
            self._emit(run.id, EventKind.PHASE, payload={"recovered": True})
            await self._drive(run.id, None)
        return len(crashed)

    async def serve(self, poll_s: float = 1.0) -> None:
        """Recover, then poll forever."""
        await self.recover()
        while True:
            if not await self.step():
                await asyncio.sleep(poll_s)

    # --- commands --------------------------------------------------------------------------------

    async def _answer_commands(self, run: Run) -> bool:
        commands = self._store.claim_commands(run.id)
        for command in commands:
            if await self._apply(run, command):
                break  # the run left the waiting state; later commands belong to its next gate
        return bool(commands)

    async def _apply(self, run: Run, command: RunCommand) -> bool:
        if command.kind is CommandKind.CANCEL:
            self._stop(run.id, StopReason.HUMAN_ABORT)
            return True
        if command.kind is CommandKind.RESUME and command.decision is not None:
            decision = command.decision
            self._store.resolve_gate(decision)
            self._emit(
                run.id,
                EventKind.GATE_RESOLVED,
                payload={"gate_id": decision.gate_id, "decision": decision.decision},
            )
            self._store.set_run_status(run.id, RunStatus.RUNNING)
            await self._drive(run.id, Command(resume=decision.decision))
            return True
        self._emit(run.id, EventKind.ERROR, payload={"ignored_command": command.kind.value})
        return False

    # --- driving the graph -----------------------------------------------------------------------

    async def _drive(self, run_id: str, graph_input: Any) -> None:
        """Run the graph until it parks, ends or is cancelled; an auto-approve run answers its own gates."""
        try:
            while True:
                gate = await self._stream(run_id, graph_input)
                if gate is None:
                    return
                if not self._store.get_run(run_id).auto_approve:
                    return
                graph_input = self._approve(run_id, gate)
        except Exception as exc:  # the worker must outlive any one run: record it and stop that run
            log.exception("run %s failed", run_id)
            self._emit(run_id, EventKind.ERROR, payload={"error": f"{type(exc).__name__}: {exc}"[:500]})
            self._stop(run_id, StopReason.INFRA_ERROR)

    async def _stream(self, run_id: str, graph_input: Any) -> GateRequest | None:
        """Stream the graph; the gate it parked at, or None when the run ended or was cancelled."""
        config = {"configurable": {"thread_id": run_id}}
        updates = self._graph.astream(graph_input, config, stream_mode="updates").__aiter__()
        while True:
            pending = asyncio.ensure_future(updates.__anext__())
            while not pending.done():
                await asyncio.wait({pending}, timeout=CANCEL_POLL_S)
                if not pending.done() and self._cancel_requested(run_id):
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                    self._stop(run_id, StopReason.HUMAN_ABORT)
                    return None
            try:
                update = pending.result()
            except StopAsyncIteration:
                break
            if (gate := self._record(run_id, update)) is not None:
                return gate  # parked at a gate
        state = (await self._graph.aget_state(config)).values
        self._stop(run_id, StopReason(state.get("stop", StopReason.INFRA_ERROR.value)))
        return None

    def _cancel_requested(self, run_id: str) -> bool:
        """Read the run's new commands while it runs; only a Cancel means anything to a run in progress."""
        cancelled = False
        for command in self._store.claim_commands(run_id):
            if command.kind is CommandKind.CANCEL:
                cancelled = True
            else:
                self._emit(run_id, EventKind.ERROR, payload={"ignored_command": command.kind.value})
        return cancelled

    def _approve(self, run_id: str, gate: GateRequest) -> Command[Any]:
        """Answer a gate for an auto-approve run: approve it, log that nobody looked, and resume."""
        decision = GateDecision(
            gate_id=gate.gate_id,
            decision=AUTO_APPROVE,
            comment="approved automatically (the run was started with auto-approve)",
            at=self._clock(),
        )
        self._store.resolve_gate(decision)
        self._emit(
            run_id,
            EventKind.GATE_RESOLVED,
            payload={"gate_id": gate.gate_id, "decision": AUTO_APPROVE, "automatic": True},
        )
        self._store.set_run_status(run_id, RunStatus.RUNNING)
        return Command(resume=AUTO_APPROVE)

    def _record(self, run_id: str, update: dict[str, Any]) -> GateRequest | None:
        """Write the events of one graph update; the gate it parked at, if the update is a gate interrupt."""
        for node, value in update.items():
            if node != "__interrupt__":
                self._emit(run_id, EventKind.NODE_END, node_id=node, payload=node_summary(value))
                continue
            gate = None
            for interrupt in value:
                gate = self._open_gate(run_id, interrupt.value)
            self._store.set_run_status(run_id, RunStatus.WAITING_GATE)
            return gate
        return None

    def _open_gate(self, run_id: str, ask: dict[str, Any]) -> GateRequest:
        for pending in self._store.pending_gates(run_id):
            if pending.gate_id == ask["gate_id"]:
                return pending  # a recovered run asks again for the gate that is already open
        request = GateRequest(
            gate_id=ask["gate_id"],
            kind=ask["kind"],
            run_id=run_id,
            options=ask["options"],
            payload=ask.get("payload", {}),
        )
        self._store.open_gate(request)
        self._emit(
            run_id, EventKind.GATE_REQUESTED, payload={"gate_id": request.gate_id, "kind": request.kind}
        )
        return request

    def _stop(self, run_id: str, reason: StopReason) -> None:
        self._emit(run_id, EventKind.STOP, payload={"stop_reason": reason.value})
        self._store.set_run_status(run_id, RunStatus.STOPPED, reason)

    def _emit(
        self, run_id: str, kind: EventKind, node_id: str | None = None, payload: dict[str, Any] | None = None
    ) -> None:
        event = RunEvent(
            run_id=run_id,
            seq=self._store.next_seq(run_id),
            ts=self._clock(),
            kind=kind,
            node_id=node_id,
            payload=payload or {},
        )
        self._store.append_events([event])
