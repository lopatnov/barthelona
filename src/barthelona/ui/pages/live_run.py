"""Live Run page: real-time event log tail and topology DOT graph.

Phase 1a features:
- Event log tail (polling from SQLite events table)
- Sprint topology DOT graph (from SprintTopology)
- Run status and stop reason
- Manual controls: cancel, and continue a run that stopped on a limit
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import streamlit as st

from barthelona.domain import CommandKind, EventKind, RunCommand, RunStatus
from barthelona.persistence import Store, open_store
from barthelona.ui.continue_run import render_continue
from barthelona.ui.event_text import describe
from barthelona.ui.package_panel import render_package_panel
from barthelona.ui.reasoning_panel import render_reasoning_panel
from barthelona.ui.run_info import render_parameters, render_run_files, render_stages, render_status_banner

_EVENT_KIND_ICONS = {
    EventKind.PHASE: "📍",
    EventKind.NODE_START: "▶️",
    EventKind.NODE_END: "✅",
    EventKind.LLM_CALL: "🤖",
    EventKind.EXEC: "⚙️",
    EventKind.DIAGNOSTICS: "🔍",
    EventKind.TEST_RESULT: "🧪",
    EventKind.GATE_REQUESTED: "⏸️",
    EventKind.GATE_RESOLVED: "✅",
    EventKind.ESCALATION: "🚨",
    EventKind.INCREMENT: "📦",
    EventKind.BUDGET: "💰",
    EventKind.STOP: "🛑",
    EventKind.ERROR: "❌",
}


def _format_event(event: Any, technical: bool = False) -> str:
    """One event as a line a person can read; *technical* adds the raw ids and payload."""
    icon = _EVENT_KIND_ICONS.get(event.kind, "•")
    if event.kind is EventKind.STOP and event.payload.get("stop_reason") == "green":
        icon = "🏁"
    line = f"{icon} `{event.ts.astimezone().strftime('%H:%M:%S')}` {describe(event)}"  # local time
    if not technical:
        return line
    details = [event.kind.value, *(str(part) for part in (event.node_id, event.task_id) if part)]
    if event.payload:
        details.append(json.dumps(event.payload, ensure_ascii=False, default=str)[:500])
    return f"{line}  \n<small>{' | '.join(details)}</small>"


def _render_topology(run_id: str, store: Store) -> None:
    """Render the sprint topology DOT graph if available."""
    # Check for topology in the run's workspace
    run = store.get_run(run_id)
    workspace = Path(run.workspace)

    topology_path = workspace / "topology.dot"
    if topology_path.exists():
        st.subheader("📊 Sprint Topology")
        dot_content = topology_path.read_text(encoding="utf-8")
        st.graphviz_chart(dot_content, use_container_width=True)
    else:
        # Check for topology in events
        events = store.events_after(run_id, after_seq=-1, limit=1000)
        for event in reversed(events):
            if event.kind == EventKind.PHASE and "topology" in event.payload:
                st.subheader("📊 Sprint Topology")
                topology = event.payload["topology"]
                if isinstance(topology, str):
                    st.graphviz_chart(topology, use_container_width=True)
                elif isinstance(topology, dict) and "dot" in topology:
                    st.graphviz_chart(topology["dot"], use_container_width=True)
                break
        else:
            st.info("Topology not yet available (run hasn't reached first sprint)")


def _render_run_controls(run_id: str, run: Any, store: Store) -> None:
    """Render manual run controls."""
    st.subheader("🎮 Run Controls")

    col1, col2, col3 = st.columns(3)

    with col1:
        can_cancel = run.status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_GATE)
        label = "⏸ Pause (Resume continues it later)" if run.status is RunStatus.RUNNING else "🛑 Cancel Run"
        if can_cancel and st.button(label, type="secondary", use_container_width=True):
            command = RunCommand(run_id=run_id, kind=CommandKind.CANCEL)
            store.enqueue_command(command)
            st.success("Stop queued: the worker frees up and starts the next queued run")
            st.rerun()
        if run.status is RunStatus.RUNNING:
            st.caption(
                "Pause drops the model request in flight and stops this run. **Resume** restarts it from "
                "its last finished step. Meanwhile the worker takes the next queued run."
            )

    with col2:
        render_continue(run, store)

    with col3:
        if run.status == RunStatus.WAITING_GATE:
            st.info("⏸️ Run is waiting at a gate")
            st.caption("Use the **Approvals** page to resolve gates")


def _get_active_runs(store: Store) -> list[Any]:
    """Get all runs including stopped ones for inspection."""
    return store.list_runs()


def _render_run_header(run: Any) -> None:
    """Render the run status header metrics."""
    col1, col2, col3, col4 = st.columns(4)
    status_colors = {
        RunStatus.QUEUED: "🟡",
        RunStatus.RUNNING: "🟢",
        RunStatus.WAITING_GATE: "🟠",
        RunStatus.DRAINING: "🔵",
        RunStatus.STOPPED: "🔴",
    }
    with col1:
        st.metric("Status", f"{status_colors.get(run.status, '⚪')} {run.status.value}")
    with col2:
        st.metric("Mode", run.mode.value)
    with col3:
        st.metric("Target", run.target.preset)
    with col4:
        st.metric("Stop Reason", run.stop_reason.value if run.stop_reason else "—")


def _render_event_log(run: Any, store: Store) -> bool:
    """Render the event log with polling controls; True when the page should refresh itself."""
    st.subheader("📜 What happened")

    # Polling controls
    col_poll1, col_poll2, col_poll3 = st.columns([2, 2, 1])
    with col_poll1:
        auto_poll = st.checkbox("Refresh every second", value=True, key="auto_poll")
    with col_poll2:
        technical = st.checkbox("Show technical details", value=False, key="event_details")
    with col_poll3:
        if st.button("🔄 Refresh Now"):
            st.rerun()

    # Session state for event history and last seen sequence
    history_key = f"event_history_{run.id}"
    seq_key = f"last_seq_{run.id}"

    if history_key not in st.session_state:
        st.session_state[history_key] = []
    if seq_key not in st.session_state:
        st.session_state[seq_key] = -1

    # Fetch new events
    events = store.events_after(run.id, after_seq=st.session_state[seq_key], limit=100)

    if events:
        st.session_state[seq_key] = events[-1].seq
        # Prepend new events to history (oldest first for display)
        for event in events:
            st.session_state[history_key].insert(0, event)
        # Keep bounded history (last 500 events)
        if len(st.session_state[history_key]) > 500:
            st.session_state[history_key] = st.session_state[history_key][:500]

    # Display accumulated event history (newest first)
    history = st.session_state[history_key]
    if history:
        st.info(f"**Now:** {describe(history[0])}")
        for event in history:
            st.markdown(_format_event(event, technical), unsafe_allow_html=technical)
    else:
        st.caption("No events yet...")

    return auto_poll


def page_live_run() -> None:
    st.header("📺 Live Run")

    store = open_store(Path("var/app.sqlite"))

    try:
        active_runs = _get_active_runs(store)

        if not active_runs:
            st.info("No active runs. Create a new run on the **New Request** page.")
            return

        # Run selector
        by_id = {r.id: r for r in reversed(active_runs)}  # newest first
        ids = list(by_id)
        active = st.session_state.get("active_run_id")
        selected_id = st.selectbox(
            "Select Run",
            options=ids,
            index=ids.index(active) if active in by_id else 0,
            format_func=lambda run_id: f"{run_id} ({by_id[run_id].status.value})",
        )
        st.session_state["active_run_id"] = selected_id  # keeps this run selected across refreshes
        run = by_id[selected_id]

        # Run status header, what it waits for, the stages and what it was started with
        _render_run_header(run)
        render_status_banner(run, store)
        render_stages(run, store)
        render_parameters(run)
        render_run_files(run)

        st.divider()

        # Run controls
        _render_run_controls(run.id, run, store)

        st.divider()

        # Package a green run
        render_package_panel(run, store)

        st.divider()

        # What happened, then the details: what the models think and answer, and the sprint graph
        auto_poll = _render_event_log(run, store)

        st.divider()
        render_reasoning_panel(run.id)

        st.divider()
        _render_topology(run.id, store)

        # Refresh last: st.rerun stops the script, so everything above must already be drawn
        if auto_poll:
            time.sleep(1)
            st.rerun()

    except Exception as e:
        st.error(f"Error loading live run: {e}")
    finally:
        store.close()


if __name__ == "__main__":
    page_live_run()
