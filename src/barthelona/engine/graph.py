"""The outer run graph (docs/architecture.md §6): fixed code, compiled once when the worker starts.

Phase 1a builds it from the front: `preflight` -> gate G1 -> `finalize`. Each later node (intake, spec,
architect, scaffold, the sprint loop) is added between the gate and `finalize` with its own tests, so no node
exists without a caller. Gate nodes make no model calls: a node re-runs from its first line when it is resumed
(§5.2).

Nodes are `async def` on purpose: a sync node runs in a worker thread, and the SQLite store belongs to the
thread that opened it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from barthelona.domain import GateKind, StopReason

APPROVE = "approve"
REJECT = "reject"
G1_OPTIONS = [APPROVE, REJECT]

# Why the target cannot run on this host, or None when it can (the toolchain resolver plugs in here).
Preflight = Callable[[str], str | None]


class RunState(TypedDict, total=False):
    run_id: str
    stop: str  # a StopReason value once the run must end
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


def build_graph(
    preflight: Preflight, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    """Compile the outer run graph with *checkpointer* (an `AsyncSqliteSaver` in the worker)."""

    async def run_preflight(state: RunState) -> dict[str, Any]:
        reason = preflight(state["run_id"])
        return {"stop": StopReason.UNSUPPORTED_TARGET.value} if reason else {}

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
    graph.add_node("g1_gate", g1_gate)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "preflight")
    graph.add_conditional_edges("preflight", _stop_or("g1_gate"), ["g1_gate", "finalize"])
    graph.add_edge("g1_gate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
