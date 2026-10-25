"""Live Run control: continue a run that stopped on a limit, with a larger limit."""

from __future__ import annotations

import streamlit as st

from barthelona.domain import CommandKind, Run, RunBudget, RunCommand, RunStatus, StopReason
from barthelona.persistence import Store

BUDGET_STOPS = frozenset({StopReason.BUDGET_TIME, StopReason.BUDGET_TOKENS, StopReason.BUDGET_COST})
EXTRA_WALL_S = 14400.0  # another 4 hours of work

_WHAT_IT_ADDS = {
    StopReason.BUDGET_TIME: "adds 4 hours of work time",
    StopReason.BUDGET_TOKENS: "doubles the token limit",
    StopReason.BUDGET_COST: "doubles the money cap",
}


def can_continue(run: Run) -> bool:
    """True for a run that stopped because a limit ran out; every other stop is final."""
    return run.status is RunStatus.STOPPED and run.stop_reason in BUDGET_STOPS


def extended_budget(run: Run) -> RunBudget:
    """The run's budget with the limit that ran out raised; the other limits stay as they were."""
    budget = run.budget
    changes: dict[str, float | int | None] = {}
    if run.stop_reason is StopReason.BUDGET_TIME:
        changes["wall_s"] = budget.wall_s + EXTRA_WALL_S
    elif run.stop_reason is StopReason.BUDGET_TOKENS:
        changes["tokens"] = budget.tokens * 2
    elif run.stop_reason is StopReason.BUDGET_COST and budget.usd:
        changes["usd"] = budget.usd * 2
    return RunBudget.model_validate(budget.model_dump() | changes)


def render_continue(run: Run, store: Store) -> None:
    """The Continue button for a run that stopped on a limit; the worker restarts the code step."""
    if not can_continue(run):
        return
    if any(waiting.id == run.id for waiting in store.runs_to_continue()):
        st.info("Continue requested: the worker picks it up within a few seconds.")
        return
    reason = run.stop_reason
    adds = _WHAT_IT_ADDS.get(reason, "raises the limit") if reason is not None else "raises the limit"
    if st.button(f"▶️ Continue ({adds})", type="primary", use_container_width=True, key=f"continue_{run.id}"):
        store.enqueue_command(
            RunCommand(run_id=run.id, kind=CommandKind.EXTEND_BUDGET, budget=extended_budget(run))
        )
        st.rerun()
