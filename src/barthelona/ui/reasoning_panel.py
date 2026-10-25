"""Live Run panel: what the models were asked, thought and answered (the worker writes the file)."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from barthelona.domain.layout import REASONING_FILE, RUNS_DIR, run_dir
from barthelona.ui.paging import PAGE_SIZES, page_controls, page_slice

PAGE_SIZE = 8  # entries per page, newest first

# "## role via route -> model (usage)", as the log writes it; "-> model" only when the router names it
_HEADING = re.compile(r"(?m)^(?=## (?:\d\d:\d\d:\d\d )?\S+ via \S+(?: -> \S+)? \()")

_PARTS = (
    ("tried first", "Tried first"),
    ("prompt", "Asked"),
    ("reasoning", "Thinking"),
    ("answer", "Answer"),
)  # in the order the log has them


def all_entries(text: str) -> list[str]:
    """Every entry of a reasoning log, oldest first; each starts with its ``## ...`` heading."""
    return [part.strip() for part in _HEADING.split(text) if part.startswith("## ")]


def split_entry(body: str) -> dict[str, str]:
    """The parts of one log entry: prompt, reasoning, answer (an older entry has no prompt)."""
    starts: list[tuple[str, int, int]] = []  # (part, where its marker starts, where its text starts)
    position = 0
    for name, _ in _PARTS:
        marker = f"### {name}\n\n"
        at = body.find(marker, position)
        if at >= 0:
            position = at + len(marker)
            starts.append((name, at, position))
    if not starts:
        return {"answer": body.strip()}  # not in the log's format: show it whole rather than fail the page
    ends = [at for _, at, _ in starts[1:]] + [len(body)]
    return {name: body[text:end].strip() for (name, _, text), end in zip(starts, ends, strict=True)}


@st.cache_data(max_entries=4, show_spinner=False)
def _entries_of(path: str, modified: float, size: int) -> list[str]:
    """The log's entries; read again only when the file changed (the arguments are the cache key)."""
    del modified, size
    return all_entries(Path(path).read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n"))


def render_reasoning_panel(run_id: str) -> None:
    """Every model call of one run, newest page first: what was asked, the thinking and the answer."""
    st.subheader("🧠 Model reasoning")
    show = st.checkbox(
        "Show what was asked and what the models think and answer",
        value=True,
        key=f"show_reasoning_{run_id}",
    )
    if not show:
        return
    path = run_dir(RUNS_DIR, run_id) / REASONING_FILE
    if not path.is_file():
        st.caption("No model has answered yet. Each call appears here as soon as its reply arrives.")
        return
    info = path.stat()
    entries = _entries_of(str(path), info.st_mtime, info.st_size)
    page, size = page_controls(f"reasoning_{run_id}", len(entries), default_size=PAGE_SIZES[0])
    start, end = page_slice(len(entries), page, size)
    for position, entry in enumerate(reversed(entries[start:end])):
        heading, _, body = entry.partition("\n")
        parts = split_entry(body.strip())
        shown = [(key, label) for key, label in _PARTS if key in parts] or [("answer", "Answer")]
        with st.expander(heading.removeprefix("## "), expanded=position == 0):
            for tab, (key, _) in zip(st.tabs([label for _, label in shown]), shown, strict=True):
                with tab:
                    st.code(parts[key], language="text", wrap_lines=True)
