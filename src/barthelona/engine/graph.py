"""The outer run graph (docs/architecture.md §6): fixed code, compiled once when the worker starts.

Phase 1a builds it from the front: `preflight` -> `intake` -> `spec` -> `test_author` ->
`validate_spec` -> gate G1 -> `codegen` -> gate G4 -> `finalize`. `codegen` is the single-module slice
(the chunk loop plus the NASM and emulator oracles); the architect, scaffold and the sprint loop go between
G1 and it later, each with its own tests, so no node exists without a caller. Gate nodes make no model
calls: a node re-runs from its first line when it is resumed (§5.2).

Nodes are `async def` on purpose: a sync node runs in a worker thread, and the SQLite store belongs to the
thread that opened it.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from barthelona.domain import GateKind, LLMCallRecord, ProjectSpec, Run, StopReason, TestCase
from barthelona.domain._base import DomainModel
from barthelona.domain.layout import SOURCE_FILE
from barthelona.engine.codegen import REPAIR_ROLE, WRITE_ROLE, generate_source
from barthelona.engine.gates import g1_payload, g4_payload
from barthelona.engine.spec import Intake, SpecError, draft_spec, run_intake
from barthelona.engine.tests_author import author_tests, validate_spec
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.hmem import HMem
from barthelona.llm.types import GatewayError
from barthelona.verification.asm_gate import AssembleResult
from barthelona.world_model import WorldModel, record_attempt, record_spec_and_tests

APPROVE = "approve"
REJECT = "reject"
G1_OPTIONS = [APPROVE, REJECT]
G4_OPTIONS = [APPROVE, REJECT]

# Why the target cannot run on this host, or None when it can (the toolchain resolver plugs in here).
Preflight = Callable[[str], str | None]


@dataclass(frozen=True)
class Services:
    """What the nodes need from the host; the worker builds it from the store and the model catalog."""

    preflight: Preflight
    gateway_for: Callable[[Run], ModelGateway]
    load_run: Callable[[str], Run]
    load_request: Callable[[str], str]
    record_call: Callable[[str, LLMCallRecord], None]
    save_spec: Callable[[str, ProjectSpec, list[TestCase]], None]
    facts: Callable[[], str]  # the knowledge-store block for the prompts ('' when none is configured)
    save_source: Callable[[str, str], None]  # (run_id, source) -> the file gate G4 shows
    save_attempt: Callable[
        [str, int, str], None
    ]  # (run_id, attempt, source) -> a draft file, kept even if rejected
    open_workspace: Callable[[str], None]  # (run_id) -> creates the project's demos/ folder at the start
    nasm: str | None  # the assembler binary, None when none was found (the oracle then stops the run)
    memory: HMem | None  # H-MEM: recalled in every chunk, written to when the oracle accepts
    world: WorldModel | None  # the shared state a run records; None: the run writes nothing (D-058)
    last_call: Callable[[str], LLMCallRecord | None]  # the run's latest model call, for provenance


class RunState(TypedDict, total=False):
    run_id: str
    stop: str  # a StopReason value once the run must end
    stop_detail: str  # why, in the words of the step that stopped it; shown with the stop, never parsed
    intake: dict[str, Any]  # the `Intake` of the request
    facts: str  # rows read from the knowledge store (Zetaris), marked as untrusted data
    spec: dict[str, Any]  # the `ProjectSpec` draft
    tests: list[dict[str, Any]]  # its acceptance `TestCase`s
    g1: str  # the decision made at gate G1
    verdict: str  # the oracle's verdict on it: pass, fail or unavailable
    g4: str  # the decision made at gate G4
    spec_model: str | None  # the model that drafted the spec, captured for World Model provenance
    test_model: str | None  # the model that authored the tests, captured for World Model provenance
    spent_s: float  # seconds the model nodes have used so far; the run's wall-clock budget is spent from it


def gate_id(run_id: str, kind: GateKind) -> str:
    """The stable id of a run's gate, so a resumed node asks for the same decision again."""
    return f"{run_id}-{kind.value}"


def _ask(
    state: RunState, kind: GateKind, options: list[str], payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Park the run at a human gate; the value the UI resumes with is the decision."""
    ask = {"gate_id": gate_id(state["run_id"], kind), "kind": kind.value, "options": options}
    decision = interrupt(ask | {"payload": payload or {}})
    return {kind.value.lower(): str(decision)}


def _stop_or(next_node: str, gate: str | None = None) -> Callable[[RunState], str]:
    """The next node, or `finalize` after a stop or, with *gate*, a rejection at that gate."""

    def route(state: RunState) -> str:
        rejected = gate is not None and cast(dict[str, Any], state).get(gate) == REJECT
        return "finalize" if state.get("stop") or rejected else next_node

    return route


async def _or_stop(step: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """The step's update, or the stop its failure maps to (a model step never crashes the run)."""
    try:
        return await step
    except GatewayError:
        return {"stop": StopReason.NO_MODEL_AVAILABLE.value}
    except SpecError as exc:
        return {"stop": StopReason.MAX_ATTEMPTS.value, "stop_detail": str(exc)[:300]}


def _timed(node: Callable[[Any, RunState], Awaitable[dict[str, Any]]]) -> Callable[..., Any]:
    """Add the node's running time to `spent_s` (gate waits for a human are not counted)."""

    @functools.wraps(node)
    async def run(self: Any, state: RunState) -> dict[str, Any]:
        started = time.monotonic()
        update = await node(self, state)
        return update | {"spent_s": state.get("spent_s", 0.0) + time.monotonic() - started}

    return run


class _Nodes:
    """The graph's nodes; each is `async def` (see the module docstring) and returns a state update."""

    def __init__(self, services: Services) -> None:
        self._services = services

    def _gateway(self, run_id: str) -> ModelGateway:
        return self._services.gateway_for(self._services.load_run(run_id))

    def _recorder(self, run_id: str) -> Callable[[LLMCallRecord], None]:
        return lambda record: self._services.record_call(run_id, record)

    def _last_model(self, run_id: str) -> str | None:
        last = self._services.last_call(run_id)
        return last.model if last is not None else None

    async def preflight(self, state: RunState) -> dict[str, Any]:
        self._services.open_workspace(state["run_id"])
        reason = self._services.preflight(state["run_id"])
        return {"stop": StopReason.UNSUPPORTED_TARGET.value} if reason else {}

    @_timed
    async def intake(self, state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        facts = await asyncio.to_thread(self._services.facts)  # a failing store ends the run as infra_error
        result = run_intake(
            self._gateway(run_id), self._services.load_request(run_id), self._recorder(run_id)
        )
        return await _or_stop(_update("intake", result)) | {"facts": facts}

    @_timed
    async def spec(self, state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        drafted = draft_spec(
            self._gateway(run_id),
            self._services.load_run(run_id),
            self._services.load_request(run_id),
            Intake.model_validate(state["intake"]),
            state.get("facts", ""),
            self._recorder(run_id),
        )
        return await _or_stop(_update("spec", drafted)) | {"spec_model": self._last_model(run_id)}

    @_timed
    async def test_author(self, state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        spec = ProjectSpec.model_validate(state["spec"])
        update = await _or_stop(self._author(run_id, spec, state.get("facts", "")))
        return update | {"test_model": self._last_model(run_id)}

    async def _author(self, run_id: str, spec: ProjectSpec, facts: str) -> dict[str, Any]:
        linked, cases = await author_tests(self._gateway(run_id), spec, facts, self._recorder(run_id))
        return {
            "spec": linked.model_dump(mode="json"),
            "tests": [case.model_dump(mode="json") for case in cases],
        }

    async def validate_spec(self, state: RunState) -> dict[str, Any]:
        spec = ProjectSpec.model_validate(state["spec"])
        cases = [TestCase.model_validate(case) for case in state["tests"]]
        if problem := validate_spec(spec, cases):
            return {"stop": StopReason.MAX_ATTEMPTS.value, "stop_detail": problem[:300]}
        self._services.save_spec(state["run_id"], spec, cases)
        self._record_spec(state["run_id"], spec, cases, state.get("spec_model"), state.get("test_model"))
        return {}

    def _record_spec(
        self,
        run_id: str,
        spec: ProjectSpec,
        cases: list[TestCase],
        spec_model: str | None,
        test_model: str | None,
    ) -> None:
        world = self._services.world
        if world is None:
            return
        world.upsert_all(record_spec_and_tests(run_id, spec, cases, spec_model, test_model))

    async def g1_gate(self, state: RunState) -> dict[str, Any]:
        return _ask(state, GateKind.G1_SPEC, G1_OPTIONS, g1_payload(state["spec"], state["tests"]))

    @_timed
    async def codegen(self, state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        spec = ProjectSpec.model_validate(state["spec"])
        self._services.open_workspace(run_id)  # a run that began before the folder existed gets it here
        wall_s = self._services.load_run(run_id).budget.wall_s
        remaining = wall_s - state.get("spent_s", 0.0)  # earlier nodes have already used part of the budget
        if remaining <= 0:
            return {"stop": StopReason.BUDGET_TIME.value}
        try:
            async with asyncio.timeout(remaining):  # the longest node: bounded by what is left of the budget
                done = await generate_source(
                    self._gateway(run_id),
                    spec,
                    [TestCase.model_validate(case) for case in state["tests"]],
                    state.get("facts", ""),
                    self._services.memory,
                    self._services.nasm,
                    self._recorder(run_id),
                    run_id,
                    lambda attempt, source, verdict, chunks: self._on_attempt(
                        run_id, spec, attempt, source, verdict, chunks
                    ),
                    self._services.world,
                )
        except TimeoutError:
            return {"stop": StopReason.BUDGET_TIME.value}
        if done.accepted:
            self._services.save_source(run_id, done.source)
        update: dict[str, Any] = {"verdict": done.verdict.status}
        return update if done.accepted else update | {"stop": done.stop.value}

    def _on_attempt(
        self,
        run_id: str,
        spec: ProjectSpec,
        attempt: int,
        source: str,
        verdict: AssembleResult,
        chunks: int,
    ) -> None:
        self._services.save_attempt(run_id, attempt, source)
        world = self._services.world
        if world is None:
            return
        route = WRITE_ROLE if attempt == 1 else REPAIR_ROLE
        world.upsert(
            record_attempt(
                run_id,
                spec.slug,
                attempt,
                verdict.status,
                verdict.errors,
                chunks,
                self._last_model(run_id),
                route,
            )
        )

    async def g4_gate(self, state: RunState) -> dict[str, Any]:
        return _ask(state, GateKind.G4_FINAL, G4_OPTIONS, g4_payload(SOURCE_FILE, state.get("verdict")))

    async def finalize(self, state: RunState) -> dict[str, Any]:
        if state.get("stop"):
            return {}
        if REJECT in (state.get("g1"), state.get("g4")):
            return {"stop": StopReason.HUMAN_ABORT.value}
        return {"stop": StopReason.GREEN.value}


async def _update(key: str, produced: Awaitable[DomainModel]) -> dict[str, Any]:
    return {key: (await produced).model_dump(mode="json")}


# The create flow so far, in order; a stop in any node skips to `finalize`, and so does a rejected gate.
_CHAIN = ("preflight", "intake", "spec", "test_author", "validate_spec", "g1_gate", "codegen", "g4_gate")
_GATES = {"g1_gate": "g1"}


def build_graph(
    services: Services, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    """Compile the outer run graph with *checkpointer* (an `AsyncSqliteSaver` in the worker)."""
    nodes = _Nodes(services)
    graph: StateGraph[RunState, None, RunState, RunState] = StateGraph(RunState)
    for name in (*_CHAIN, "finalize"):
        graph.add_node(name, getattr(nodes, name))
    graph.add_edge(START, _CHAIN[0])
    for here, after in pairwise(_CHAIN):
        graph.add_conditional_edges(here, _stop_or(after, _GATES.get(here)), [after, "finalize"])
    graph.add_edge(_CHAIN[-1], "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
