"""Live Run's World Model panel: the entities a run has recorded so far (D-058).

The panel reads the same file-backed store the worker writes, so it imports no engine or LangGraph; the UI is
allowed `world_model` by the D-045 layering table.
"""

from __future__ import annotations

import json

import streamlit as st

from barthelona.world_model import DEFAULT_STORE, WorldModel


def render_world_panel(run_id: str) -> None:
    """Show the run's requirement, test and attempt entities, each with its provenance."""
    st.subheader("🌐 World Model")
    if not DEFAULT_STORE.exists():
        st.caption("No World Model store yet — the worker writes it as the run goes.")
        return
    store = WorldModel(DEFAULT_STORE)
    try:
        entities = store.entities(run_id=run_id)
    finally:
        store.close()
    if not entities:
        st.caption("No entities recorded for this run yet.")
        return
    for entity in entities:
        st.markdown(f"**{entity.kind}** `{entity.key}`")
        st.code(json.dumps(entity.attrs, indent=2, ensure_ascii=False, default=str), language="json")
        st.caption(
            f"provenance: model={entity.provenance.by or '?'}, "
            f"route={entity.provenance.route or '?'}, at={entity.provenance.at}"
        )
