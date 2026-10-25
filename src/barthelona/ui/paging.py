"""Paging for Live Run lists that show the newest entry first: every entry stays reachable."""

from __future__ import annotations

import streamlit as st

PAGE_SIZES = (10, 25, 50, 100)


def page_count(total: int, size: int) -> int:
    """How many pages *total* entries make at *size* per page (at least one)."""
    return max(1, -(-total // size))


def page_slice(total: int, page: int, size: int) -> tuple[int, int]:
    """Start and end positions, counted from the oldest entry, of page *page* (0 = newest) of the list."""
    page = min(max(page, 0), page_count(total, size) - 1)
    end = total - page * size
    return max(0, end - size), end


def page_controls(key: str, total: int, default_size: int) -> tuple[int, int]:
    """Draw 'per page', Newer and Older and the page label; the chosen page (0 = newest) and page size."""
    size = st.selectbox(
        "Per page",
        PAGE_SIZES,
        index=PAGE_SIZES.index(default_size),
        key=f"{key}_size",
    )
    pages = page_count(total, size)
    page = min(st.session_state.get(f"{key}_page", 0), pages - 1)
    left, middle, right = st.columns([1, 2, 1])
    with left:
        if st.button("⬅ Newer", key=f"{key}_newer", disabled=page == 0):
            page -= 1
    with right:
        if st.button("Older ➡", key=f"{key}_older", disabled=page >= pages - 1):
            page += 1
    st.session_state[f"{key}_page"] = page
    with middle:
        st.caption(f"Page {page + 1} of {pages}; {total} entries in all, newest first")
    return page, size
