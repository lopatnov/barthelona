"""Live Run panel: what the models were asked, thought and answered (the worker writes the file)."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from barthelona.domain.layout import REASONING_FILE, RUNS_DIR, run_dir

MAX_ENTRIES = 8  # newest first; the whole log stays in the run folder
_TAIL_BYTES = 800_000  # read only the end of a long log; an entry can hold a whole prompt

# "## role via route -> model (usage)", as the log writes it; "-> model" only when the router names it
_HEADING = re.compile(r"(?m)^(?=## (?:\d\d:\d\d:\d\d )?\S+ via \S+(?: -> \S+)? \()")

_PARTS = (
    ("tried first", "Tried first"),
    ("prompt", "Asked"),
    ("reasoning", "Thinking"),
    ("answer", "Answer"),
)  # in the order the log has them


def latest_entries(text: str, limit: int = MAX_ENTRIES) -> list[str]:
    """The last *limit* entries of a reasoning log, newest first; each starts with its ``## ...`` heading."""
    entries = [part.strip() for part in _HEADING.split(text) if part.startswith("## ")]
    return entries[-limit:][::-1]


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


def _read_tail(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - _TAIL_BYTES))
        return handle.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


def render_reasoning_panel(run_id: str) -> None:
    """The newest model calls of one run: what was asked, the thinking and the answer; on by default."""
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
    for position, entry in enumerate(latest_entries(_read_tail(path))):
        heading, _, body = entry.partition("\n")
        parts = split_entry(body.strip())
        shown = [(key, label) for key, label in _PARTS if key in parts] or [("answer", "Answer")]
        with st.expander(heading.removeprefix("## "), expanded=position == 0):
            for tab, (key, _) in zip(st.tabs([label for _, label in shown]), shown, strict=True):
                with tab:
                    st.code(parts[key], language="text", wrap_lines=True)
