"""Live Run panel: what the models were asked, thought and answered (the worker writes the file)."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from barthelona.domain.layout import REASONING_FILE, RUNS_DIR, run_dir

PAGE_SIZE = 10  # calls shown at once; the page box reaches all the others, newest first

# "## role via route -> model (usage)", as the log writes it; "-> model" only when the router names it
_HEADING = re.compile(r"(?m)^(?=## (?:\d\d:\d\d:\d\d )?\S+ via \S+(?: -> \S+)? \()")

_PARTS = (
    ("tried first", "Tried first"),
    ("prompt", "Asked"),
    ("reasoning", "Thinking"),
    ("answer", "Answer"),
)  # in the order the log has them


def latest_entries(text: str, limit: int | None = None) -> list[str]:
    """The entries of a reasoning log, newest first (only *limit* when given), each with its heading."""
    entries = [part.strip() for part in _HEADING.split(text) if part.startswith("## ")]
    newest_first = entries[::-1]
    return newest_first if limit is None else newest_first[:limit]


def pages(total: int, size: int = PAGE_SIZE) -> int:
    """How many pages *total* entries make; at least one, so an empty log still has a page 1."""
    return max(1, -(-total // size))


def page_slice(entries: list[str], page: int, size: int = PAGE_SIZE) -> list[str]:
    """The entries of 1-based *page*, newest first; a page past the end is clamped to the last one."""
    page = min(max(page, 1), pages(len(entries), size))
    return entries[(page - 1) * size : page * size]


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


@st.cache_data(show_spinner=False, max_entries=8)
def _entries_of(path: str, modified_ns: int, size: int) -> list[str]:
    """Every entry of the log at *path*, newest first; the page reruns each second, the file changes less."""
    text = Path(path).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return latest_entries(text)


def _render_entry(position: int, entry: str) -> None:
    heading, _, body = entry.partition("\n")
    parts = split_entry(body.strip())
    shown = [(key, label) for key, label in _PARTS if key in parts] or [("answer", "Answer")]
    with st.expander(heading.removeprefix("## "), expanded=position == 0):
        for tab, (key, _) in zip(st.tabs([label for _, label in shown]), shown, strict=True):
            with tab:
                st.code(parts[key], language="text", wrap_lines=True)


def render_reasoning_panel(run_id: str) -> None:
    """Every model call of one run, ten at a time, newest first: asked, thinking, answer; on by default."""
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
    entries = _entries_of(str(path), info.st_mtime_ns, info.st_size)
    last_page = pages(len(entries))
    page = 1
    if last_page > 1:
        page = int(
            st.number_input(
                f"Page (of {last_page}; page 1 has the newest calls)",
                min_value=1,
                max_value=last_page,
                value=1,
                step=1,
                key=f"reasoning_page_{run_id}",
            )
        )
    first = (page - 1) * PAGE_SIZE + 1
    st.caption(
        f"Calls {first} to {first + len(page_slice(entries, page)) - 1} of {len(entries)}, newest first."
    )
    for position, entry in enumerate(page_slice(entries, page)):
        _render_entry(position if page == 1 else 1, entry)
