"""Streamlit UI entry point for barthelona (docs/architecture.md §17).

Pages (Phase 1a):
- New Request: dialect/preset picker, create/edit mode, prompt
- Approvals: gate G1/G2/G4 rendering
- Live Run: event log tail, topology DOT graph

Phase 1b adds: Sprint board, Review, Toolchains & models, Runs.
"""

from __future__ import annotations

import streamlit as st

from barthelona.ui.navigation import PAGES_KEY
from barthelona.ui.pages.approvals import page_approvals
from barthelona.ui.pages.live_run import page_live_run
from barthelona.ui.pages.new_request import page_new_request


def main() -> None:
    st.set_page_config(
        page_title="barthelona",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize session state for run tracking
    if "active_run_id" not in st.session_state:
        st.session_state.active_run_id = None
    if "event_poll_interval" not in st.session_state:
        st.session_state.event_poll_interval = 1.0  # seconds

    # Define pages using st.Page for proper multipage navigation
    new_request = st.Page(page_new_request, title="New Request", icon="📝")
    approvals = st.Page(page_approvals, title="Approvals", icon="✅")
    live_run = st.Page(page_live_run, title="Live Run", icon="📊")
    # Pages jump to each other with st.switch_page, which needs the Page objects.
    st.session_state[PAGES_KEY] = {"approvals": approvals, "live_run": live_run}

    pg = st.navigation({"Navigation": [new_request, approvals, live_run]})
    pg.run()


if __name__ == "__main__":
    main()
