"""The outer run graph (docs/architecture.md §6): fixed code, compiled once when the worker starts.

Phase 1a builds it from the front: `preflight` -> `intake` -> `spec` -> gate G1 -> `finalize`. Each later
node (test author, architect, scaffold, the sprint loop) is added between the gate and `finalize` with its own
tests, so no node exists without a caller. Gate nodes make no model calls: a node re-runs from its first
line when it is resumed (§5.2).

Nodes are `async def` on purpose: a sync node runs in a worker thread, and the SQLite store belongs to the
thread that opened it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from barthelona.domain import GateKind, LLMCallRecord, ProjectSpec, Run, StopReason
from barthelona.engine.spec import Intake, SpecError, draft_spec, run_intake
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.types import GatewayError

APPROVE = "approve"
REJECT = "reject"
G1_OPTIONS = [APPROVE, REJECT]

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
    save_spec: Callable[[str, ProjectSpec], None]


class RunState(TypedDict, total=False):
    run_id: str
    stop: str  # a StopReason value once the run must end
    intake: dict[str, Any]  # the `Intake` of the request
    g1: str  # the decision made at gate G1


def gate_id(run_id: str, kind: GateKind) -> str:
    """The stable id of a run's gate, so a resumed node asks for the same decision again."""
    return f"{run_id}-{kind.value}"


def _ask(state: RunState, kind: GateKind, options: list[str]) -> dict[str, Any]:
    """Park the run at a human gate; the value the UI resumes with is the decision."""
    decision = interrupt({"gate_id": gate_id(state["run_id"], kind), "kind": kind.value, "options": options})
    return {kind.value.lower(): str(decision)}


def _stop_or(next_node: str) -> Callable[[RunState], str]:
    return lambda state: "finalize" if state.get("stop") else next_node


async def _or_stop(step: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """The step's update, or the stop its failure maps to (a model step never crashes the run)."""
    try:
        return await step
    except GatewayError:
        return {"stop": StopReason.NO_MODEL_AVAILABLE.value}
    except SpecError:
        return {"stop": StopReason.MAX_ATTEMPTS.value}


def build_graph(
    services: Services, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    """Compile the outer run graph with *checkpointer* (an `AsyncSqliteSaver` in the worker)."""

    async def run_preflight(state: RunState) -> dict[str, Any]:
        reason = services.preflight(state["run_id"])
        return {"stop": StopReason.UNSUPPORTED_TARGET.value} if reason else {}

    async def intake(state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        run = services.load_run(run_id)

        async def step() -> dict[str, Any]:
            result = await run_intake(
                services.gateway_for(run),
                services.load_request(run_id),
                lambda record: services.record_call(run_id, record),
            )
            return {"intake": result.model_dump(mode="json")}

        return await _or_stop(step())

    async def spec(state: RunState) -> dict[str, Any]:
        run_id = state["run_id"]
        run = services.load_run(run_id)

        async def step() -> dict[str, Any]:
            drafted = await draft_spec(
                services.gateway_for(run),
                run,
                services.load_request(run_id),
                Intake.model_validate(state["intake"]),
                lambda record: services.record_call(run_id, record),
            )
            services.save_spec(run_id, drafted)
            return {}

        return await _or_stop(step())

    async def g1_gate(state: RunState) -> dict[str, Any]:
        return _ask(state, GateKind.G1_SPEC, G1_OPTIONS)

    async def finalize(state: RunState) -> dict[str, Any]:
        if state.get("stop"):
            return {}
        if state.get("g1") == REJECT:
            return {"stop": StopReason.HUMAN_ABORT.value}
        raise NotImplementedError("the create flow after gate G1 is not built yet (Phase 1a, next slices)")

    graph: StateGraph[RunState, None, RunState, RunState] = StateGraph(RunState)
    graph.add_node("preflight", run_preflight)
    graph.add_node("intake", intake)
    graph.add_node("spec", spec)
    graph.add_node("g1_gate", g1_gate)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "preflight")
    graph.add_conditional_edges("preflight", _stop_or("intake"), ["intake", "finalize"])
    graph.add_conditional_edges("intake", _stop_or("spec"), ["spec", "finalize"])
    graph.add_conditional_edges("spec", _stop_or("g1_gate"), ["g1_gate", "finalize"])
    graph.add_edge("g1_gate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
