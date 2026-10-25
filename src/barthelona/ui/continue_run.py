"""Live Run control: continue a run stopped on a limit (with a bigger one) or resume any other stopped run."""

from __future__ import annotations

import streamlit as st

from barthelona.domain import CommandKind, Run, RunBudget, RunCommand, RunStatus, StopReason
from barthelona.persistence import Store

FINAL_STOPS = frozenset({StopReason.GREEN, StopReason.UNSUPPORTED_TARGET})  # nothing to resume
EXTRA_WALL_S = 14400.0  # another 4 hours of work

_CONTINUE_LABELS = {
    StopReason.BUDGET_TIME: "▶️ Continue (adds 4 hours of work time)",
    StopReason.BUDGET_TOKENS: "▶️ Continue (doubles the token limit)",
    StopReason.BUDGET_COST: "▶️ Continue (doubles the money cap)",
    StopReason.HUMAN_ABORT: "▶️ Resume (you cancelled it; the code step starts again)",
    StopReason.MAX_ATTEMPTS: "▶️ Resume (try the code step again)",
}


def can_continue(run: Run) -> bool:
    """True for a stopped run the worker can restart: every stop except a finished or an unsupported run."""
    return (
        run.status is RunStatus.STOPPED and run.stop_reason is not None and run.stop_reason not in FINAL_STOPS
    )


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
    """The Continue / Resume button of a stopped run; the worker restarts the code step."""
    if not can_continue(run):
        return
    if any(waiting.id == run.id for waiting in store.runs_to_continue()):
        st.info("Resume requested: the worker picks it up within a few seconds.")
        return
    reason = run.stop_reason
    label = _CONTINUE_LABELS.get(reason, "▶️ Resume (the code step starts again)") if reason else "▶️ Resume"
    if st.button(label, type="primary", use_container_width=True, key=f"continue_{run.id}"):
        store.enqueue_command(
            RunCommand(run_id=run.id, kind=CommandKind.EXTEND_BUDGET, budget=extended_budget(run))
        )
        st.rerun()
