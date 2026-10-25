"""Live Run blocks that answer 'what is this run, where is it, and what do I do now'."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import streamlit as st

from barthelona.domain import EventKind, Run, RunEvent, RunStatus, StopReason
from barthelona.domain.layout import (
    REASONING_FILE,
    REQUEST_FILE,
    RUNS_DIR,
    SOURCE_FILE,
    SPEC_FILE,
    TESTS_FILE,
    run_dir,
)
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


def stage_line(
    done_nodes: Iterable[str], active: bool, failed: str | None = None, automatic: bool = False
) -> str:
    """The stages as one line: done, the one in progress (while *active*), the one that *failed*, the rest.

    With *automatic* the approvals are labeled as answered by the worker, not waiting for a person.
    """
    done = set(done_nodes)
    current = next((node for node, _ in STAGES if node not in done), None) if active else None
    marks = []
    for node, label in STAGES:
        if automatic and node.endswith("_gate"):
            label = label.replace("Your approval", "Automatic approval")
        mark = "❌" if node == failed else "✅" if node in done else "⏳" if node == current else "◻️"
        marks.append(f"{mark} {label}")
    return "  →  ".join(marks)


def _done_nodes(events: Iterable[RunEvent]) -> set[str]:
    return {e.node_id for e in events if e.kind is EventKind.NODE_END and e.node_id}


def _failed_stage(run: Run, done: set[str]) -> str | None:
    """The stage a run stopped in: a node also ends when it stops the run, so the last one done is it."""
    if run.status is not RunStatus.STOPPED or run.stop_reason in (None, StopReason.GREEN):
        return None
    finished = [node for node, _ in STAGES if node in done and node != "finalize"]
    return finished[-1] if finished else None


def render_stages(run: Run, store: Store) -> None:
    events = store.events_after(run.id, after_seq=-1, limit=500)
    active = run.status in (RunStatus.RUNNING, RunStatus.QUEUED)
    done = _done_nodes(events)
    st.markdown(stage_line(done, active, _failed_stage(run, done), run.auto_approve))


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


RUN_FILES = (
    (REQUEST_FILE, "your request, as the form saved it"),
    (SPEC_FILE, "the specification; appears after the spec step"),
    (TESTS_FILE, "the acceptance tests; appear with the specification"),
    (
        SOURCE_FILE,
        "the generated program; appears only when the code step ends, which can take 10 to 20 minutes",
    ),
    (
        "attempt-N.asm",
        "every draft the model wrote, accepted or not; a stopped run has these but no main.asm",
    ),
    (REASONING_FILE, "what the models thought and answered; grows with every reply"),
)


def file_rows(folder: Path) -> list[tuple[str, str, str]]:
    """(name, state, meaning) for each file a run writes: its size and time when it exists, else 'not yet'."""
    rows = []
    for name, meaning in RUN_FILES:
        found = sorted(folder.glob(name.replace("N", "*"))) if "N" in name else [folder / name]
        existing = [path for path in found if path.is_file()]
        if not existing:
            rows.append((name, "not yet", meaning))
        rows.extend((path.name, _size_and_time(path), meaning) for path in existing)
    return rows


def _size_and_time(path: Path) -> str:
    info = path.stat()
    return f"{info.st_size} bytes, {datetime.fromtimestamp(info.st_mtime).strftime('%H:%M:%S')}"


def render_run_files(run: Run) -> None:
    """Where the run's files are and which of them exist yet."""
    folder = run_dir(RUNS_DIR, run.id)
    with st.expander("Run files: what this run has written so far", expanded=True):
        st.markdown(f"Folder: `{folder.resolve()}`")
        rows = file_rows(folder)
        st.table(
            {
                "File": [row[0] for row in rows],
                "State": [row[1] for row in rows],
                "What it is": [row[2] for row in rows],
            }
        )
        st.caption(
            f"The project folder `{run.workspace}` is written only when the run is green: automatically if "
            "the request asked for it, otherwise with **Package into demos/** (see below)."
        )
