"""Live Run panel: what the models thought and answered during a run (the worker writes the file)."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from barthelona.domain.layout import REASONING_FILE, RUNS_DIR, run_dir

MAX_ENTRIES = 8  # newest first; the whole log stays in the run folder
_TAIL_BYTES = 400_000  # read only the end of a long log


_HEADING = re.compile(r"(?m)^(?=## \S+ via \S+ \()")  # "## role via route (usage)", as the log writes it


def latest_entries(text: str, limit: int = MAX_ENTRIES) -> list[str]:
    """The last *limit* entries of a reasoning log, newest first; each starts with its ``## ...`` heading."""
    entries = [part.strip() for part in _HEADING.split(text) if part.startswith("## ")]
    return entries[-limit:][::-1]


def _read_tail(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - _TAIL_BYTES))
        return handle.read().decode("utf-8", errors="replace")


def render_reasoning_panel(run_id: str) -> None:
    """The newest model replies of one run, with the thinking and the answer; on by default."""
    st.subheader("🧠 Model reasoning")
    show = st.checkbox("Show what the models think and answer", value=True, key=f"show_reasoning_{run_id}")
    if not show:
        return
    path = run_dir(RUNS_DIR, run_id) / REASONING_FILE
    if not path.is_file():
        st.caption("No model has answered yet. Each reply appears here as soon as it arrives.")
        return
    entries = latest_entries(_read_tail(path))
    for position, entry in enumerate(entries):
        heading, _, body = entry.partition("\n")
        with st.expander(heading.removeprefix("## "), expanded=position == 0):
            st.markdown(body)
