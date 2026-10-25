"""Live Run: the danger zone, where a stopped run and its files can be removed."""

from __future__ import annotations

import shutil

import streamlit as st

from barthelona.domain import Run, RunStatus
from barthelona.domain.layout import RUNS_DIR, run_dir
from barthelona.persistence import Store


def can_remove(run: Run) -> bool:
    """Only a stopped run: a queued, running or waiting run belongs to the worker (cancel it first)."""
    return run.status is RunStatus.STOPPED


def remove_run(run: Run, store: Store) -> None:
    """Delete the run's records, then its run folder; the project folder under demos/ is never touched."""
    store.delete_run(run.id)
    shutil.rmtree(run_dir(RUNS_DIR, run.id), ignore_errors=True)  # a missing folder is fine


def render_danger_zone(run: Run, store: Store) -> None:
    """The 'Remove this run' control, behind an expander and a confirmation box."""
    with st.expander("⚠️ Danger zone"):
        st.markdown(
            f"**Remove run `{run.id}`.** Deletes its record, its events, its model-call ledger and the "
            f"folder `{run_dir(RUNS_DIR, run.id)}` (request, specification, tests, every attempt, the "
            f"reasoning log). The project folder `{run.workspace}` and the drafts in it are **not** touched. "
            "This cannot be undone."
        )
        if not can_remove(run):
            st.info("This run is not stopped. Press **Cancel Run** first; then it can be removed.")
            return
        sure = st.checkbox("I understand: remove this run for good", key=f"remove_sure_{run.id}")
        if st.button("🗑️ Remove run", disabled=not sure, type="primary", key=f"remove_{run.id}"):
            remove_run(run, store)
            st.session_state.pop("active_run_id", None)
            st.rerun()
