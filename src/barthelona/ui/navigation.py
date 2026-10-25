"""Jumping from one page to another: the app registers its pages, a page asks for one by name."""

from __future__ import annotations

import streamlit as st

PAGES_KEY = "pages"


def open_page(name: str) -> None:
    """Switch to the page registered as *name*; does nothing when the page is not registered (a test)."""
    page = st.session_state.get(PAGES_KEY, {}).get(name)
    if page is not None:
        st.switch_page(page)
