"""Live Run danger zone: remove a run and its files for good."""

from __future__ import annotations

import shutil

import streamlit as st

from barthelona.domain import Run, RunStatus
from barthelona.domain.layout import RUNS_DIR, run_dir
from barthelona.persistence import Store


def remove_run(run: Run, store: Store) -> None:
    """Delete the run's rows and its folder under var/runs/; the project folder in demos/ stays."""
    store.delete_run(run.id)
    shutil.rmtree(run_dir(RUNS_DIR, run.id), ignore_errors=True)


def render_danger_zone(run: Run, store: Store) -> None:
    """A collapsed section with one irreversible action: Remove run."""
    with st.expander("⚠️ Danger zone"):
        if run.status is RunStatus.RUNNING:
            st.caption("This run is running. Pause it first, then it can be removed.")
            return
        st.markdown(
            f"**Remove run `{run.id}`** deletes its history (events, model calls, approvals) and the files "
            f"in `{run_dir(RUNS_DIR, run.id)}`, including the reasoning log and the drafts kept there. "
            f"The project folder `{run.workspace}` is **not** touched. This cannot be undone."
        )
        sure = st.checkbox("I understand", key=f"remove_sure_{run.id}")
        if st.button("🗑 Remove run", type="secondary", disabled=not sure, key=f"remove_{run.id}"):
            remove_run(run, store)
            st.session_state.pop("active_run_id", None)
            st.rerun()
