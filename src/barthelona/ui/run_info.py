"""Live Run blocks that answer 'what is this run, where is it, and what do I do now'."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from barthelona.domain import EventKind, Run, RunEvent, RunStatus, StopReason
from barthelona.domain.layout import (
    DRAFTS_DIR,
    REASONING_FILE,
    REQUEST_FILE,
    RUNS_DIR,
    SOURCE_FILE,
    SPEC_FILE,
    TESTS_FILE,
    run_dir,
)
from barthelona.persistence import Store
from barthelona.ui.activity import activity_text, last_activity
from barthelona.ui.bounds import REAL_BOUNDS
from barthelona.ui.event_text import GATES, describe, stop_text

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

_STALE_HINT = (
    "A single model call can take a few minutes, but this is longer. Check that the worker window is still "
    "open and that Nightshift is online (`python -m barthelona meterless status`); if both are fine, wait a "
    "little more or press **Cancel Run** and then **Resume**."
)


def activity_line(last: RunEvent | None, now: datetime) -> str:
    """When the run last wrote anything and what that was: tells a long model wait from a hang."""
    if last is None:
        return "No activity recorded yet."
    seconds = max(0, int((now - last.ts).total_seconds()))
    return (
        f"Last event at {last.ts.astimezone().strftime('%H:%M:%S')} ({seconds} s ago): {describe(last)}. "
        "A model request can take many minutes; if it fails or is repeated, a line here says so."
    )


def failure_line(events: Iterable[RunEvent]) -> str:
    """How many model requests failed or were repeated, and when the last one did."""
    failed = [
        e for e in events if e.kind is EventKind.LLM_CALL and "FAILED" in str(e.payload.get("status", ""))
    ]
    if not failed:
        return "Model failures so far: none."
    return f"Model failures so far: {len(failed)}, last at {failed[-1].ts.astimezone().strftime('%H:%M:%S')}."


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
        st.info(queued_text(run, store.list_runs(RunStatus.RUNNING)))
    elif run.status is RunStatus.RUNNING:
        newest = _newest_event(run, store)
        now = datetime.now(UTC)
        last_event = newest.ts if newest else None
        sentence, stale = activity_text(last_activity(run_dir(RUNS_DIR, run.id), last_event), now)
        failures = failure_line(store.events_after(run.id, after_seq=-1, limit=5000))
        body = (
            f"**Running.** {sentence} {_STALE_HINT if stale else _HOW_LONG}\n\n"
            f"{activity_line(newest, now)}\n\n{failures}"
        )
        (st.warning if stale else st.info)(body)
    elif run.status is RunStatus.STOPPED and run.stop_reason is not None:
        text = stop_text(run.stop_reason.value)
        if run.stop_reason is StopReason.GREEN:
            st.success(text)
        else:
            st.error(text)


def _newest_event(run: Run, store: Store) -> RunEvent | None:
    newest = store.events_after(run.id, after_seq=max(store.next_seq(run.id) - 2, -1), limit=5)
    return newest[-1] if newest else None


def queued_text(run: Run, running: list[Run]) -> str:
    """Why a queued run has not started: the worker handles one run at a time, so it may be busy."""
    others = [other for other in running if other.id != run.id]
    if not others:
        return (
            "**Queued.** The worker has not picked this run up yet. The worker is the process that talks to "
            "the models: it is started by `scripts/run.ps1`, or by hand with `python -m barthelona worker`."
        )
    busy = others[0]
    return (
        f"**Queued behind `{busy.id}`** (project `{busy.workspace}`, still running). The worker runs one run "
        "at a time and starts this one when that run stops. To start this one now, open the other run in "
        "**Select Run** above and press **Cancel Run**; you can **Resume** it later (its current code step "
        "starts again)."
    )


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
            f"- **Limits:** {budget.wall_s:.0f} s, {budget.tokens} tokens, "
            f"{'cap $' + format(budget.usd, '.2f') if budget.usd else 'no money cap'}. {REAL_BOUNDS}\n"
            f"- **Checkpoints G1 and G4:** "
            f"{'approved automatically' if run.auto_approve else 'you approve them on the Approvals page'}\n"
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


def draft_rows(drafts: Path) -> list[tuple[str, str]]:
    """(name, size and time) of every file in the project's drafts folder, oldest name first."""
    if not drafts.is_dir():
        return []
    return [(path.name, _size_and_time(path)) for path in sorted(drafts.iterdir()) if path.is_file()]


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
        drafts = Path(run.workspace) / DRAFTS_DIR
        st.markdown(f"Project folder: `{Path(run.workspace).resolve()}` (created when the run started)")
        draft_files = draft_rows(drafts)
        if draft_files:
            st.table(
                {
                    "Draft in `drafts/`": [row[0] for row in draft_files],
                    "State": [row[1] for row in draft_files],
                }
            )
        else:
            st.caption(
                "`drafts/` holds every code draft the models write, visible as soon as the code step starts."
            )
        st.caption(
            "The rest of the project (src/, tests/, README, CI) is written when the run is green: "
            "automatically if the request asked for it, otherwise with **Package into demos/** (see below)."
        )
