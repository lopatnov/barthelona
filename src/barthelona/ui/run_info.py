"""Live Run blocks that answer 'what is this run, where is it, and what do I do now'."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from barthelona.domain import EventKind, Run, RunEvent, RunStatus, StopReason
from barthelona.domain.layout import REQUEST_FILE, RUNS_DIR, run_dir
from barthelona.persistence import Store
from barthelona.ui.event_text import GATES, stop_text

STAGES = (
    ("preflight", "Preflight"),
    ("intake", "Understand the request"),
    ("spec", "Write the specification"),
    ("test_author", "Write the tests"),
    ("validate_spec", "Check them"),
    ("g1_gate", "Your approval: G1"),
    ("codegen", "Write and check the program"),
    ("g4_gate", "Your approval: G4"),
    ("finalize", "Finish"),
)

_GATE_HELP = {
    "G1": (
        "G1 is the first checkpoint. The models have turned your request into a specification and acceptance "
        "tests; before any code is written, you read them and approve or reject. Approving locks the tests: "
        "the program is then judged against exactly these."
    ),
    "G4": (
        "G4 is the last checkpoint. The program was assembled and passed the tests in the emulator; you read "
        "the finished code and approve or reject it."
    ),
}

_HOW_LONG = (
    "On the free Nemotron lanes the first checkpoint usually comes after 2 to 5 minutes, and writing the "
    "program takes 5 to 20 minutes, more when it needs repair rounds."
)


def stage_line(done_nodes: Iterable[str], active: bool) -> str:
    """The stages as one line: done, the one in progress (while *active*), and the ones still to come."""
    done = set(done_nodes)
    current = next((node for node, _ in STAGES if node not in done), None) if active else None
    marks = []
    for node, label in STAGES:
        mark = "✅" if node in done else "⏳" if node == current else "◻️"
        marks.append(f"{mark} {label}")
    return "  →  ".join(marks)


def _done_nodes(events: Iterable[RunEvent]) -> set[str]:
    return {e.node_id for e in events if e.kind is EventKind.NODE_END and e.node_id}


def render_stages(run: Run, store: Store) -> None:
    events = store.events_after(run.id, after_seq=-1, limit=500)
    active = run.status in (RunStatus.RUNNING, RunStatus.QUEUED)
    st.markdown(stage_line(_done_nodes(events), active))


def render_status_banner(run: Run, store: Store) -> None:
    """One box that says what the run is waiting for and what the person should do."""
    if run.status is RunStatus.WAITING_GATE:
        kinds: list[str] = [str(gate.kind) for gate in store.pending_gates(run.id)] or ["G1"]
        names = ", ".join(f"{kind}: {GATES.get(kind, 'a decision')}" for kind in kinds)
        st.warning(
            f"**Waiting for your approval: {names}.** Open the **Approvals** page.\n\n"
            + " ".join(_GATE_HELP.get(kind, "") for kind in kinds)
        )
    elif run.status is RunStatus.QUEUED:
        st.info(
            "**Queued.** The worker has not picked this run up yet. The worker is the process that talks to "
            "the models: it is started by `scripts/run.ps1`, or by hand with `python -m barthelona worker`."
        )
    elif run.status is RunStatus.RUNNING:
        st.info(f"**Running.** {_HOW_LONG}")
    elif run.status is RunStatus.STOPPED and run.stop_reason is not None:
        text = stop_text(run.stop_reason.value)
        if run.stop_reason is StopReason.GREEN:
            st.success(text)
        else:
            st.error(text)


def _request_text(run: Run) -> str:
    path = run_dir(RUNS_DIR, run.id) / REQUEST_FILE
    return (
        path.read_text(encoding="utf-8") if path.is_file() else "(the request file is not in the run folder)"
    )


def render_parameters(run: Run) -> None:
    """What the run was started with, and where it runs."""
    budget = run.budget
    with st.expander("Run parameters: what this run was started with and where it runs", expanded=True):
        st.markdown(
            f"- **Run:** `{run.id}`\n"
            f"- **Project folder:** `{run.workspace}`\n"
            f"- **Target:** {run.target.preset} ({run.target.dialect.value}, {run.target.arch.value}, "
            f"{run.target.os.value})\n"
            f"- **Model profile:** {run.profile.value}; cloud providers "
            f"{'allowed' if budget.cloud_allowed else 'not allowed'}\n"
            f"- **Limits:** {budget.wall_s:.0f} s, {budget.tokens} tokens, {budget.max_sprints} sprints, "
            f"{'cap $' + format(budget.usd, '.2f') if budget.usd else 'no money cap'}\n"
            f"- **Training data collected:** {'yes' if run.collect_training_data else 'no'}\n"
            f"- **Where it runs:** in the worker process on this PC. It sends the model requests to the "
            f"provider of the profile (for Meterless: Nightshift), assembles with NASM and runs the tests in "
            f"the emulator on this PC. The run's files are in `{run_dir(RUNS_DIR, run.id)}`."
        )
        st.caption("The request, as the worker reads it:")
        st.code(_request_text(run), language="text", wrap_lines=True)
