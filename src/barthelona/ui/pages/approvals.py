"""Approvals page: review and resolve human gates (G1, G2, G4).

Phase 1a gates:
- G1_SPEC: approve the project specification (ProjectSpec)
- G2_CONTRACTS: approve the contracts.yaml (function signatures, data layout)
- G4_FINAL: final acceptance of the completed increment

The UI polls for open gates and presents their payload with decision options.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import streamlit as st

from barthelona.domain import GateDecision, GateKind, RunStatus
from barthelona.persistence import Store, open_store


def _format_payload(payload: dict[Any, Any] | list[Any]) -> str:
    """Pretty-print a gate payload as JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _render_gate_request(store: Store, gate: Any, run: Any) -> bool:
    """Render a single gate request and return True if a decision was made."""
    kind = gate.kind
    gate_id = gate.gate_id

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"{kind.value}: {kind.name.replace('_', ' ').title()}")
            st.caption(f"Gate ID: `{gate_id}` | Run: `{run.id}` | Status: `{run.status.value}`")
        with col2:
            if st.button("Refresh", key=f"refresh_{gate_id}"):
                st.rerun()

        # Render payload based on gate kind
        if kind == GateKind.G1_SPEC:
            _render_g1_spec(gate, run)
        elif kind == GateKind.G2_CONTRACTS:
            _render_g2_contracts(gate, run)
        elif kind == GateKind.G4_FINAL:
            _render_g4_final(gate, run)
        else:
            st.json(gate.payload)

        st.divider()

        # Decision buttons
        st.write("**Decision**")
        decision_cols = st.columns(len(gate.options))
        for i, option in enumerate(gate.options):
            with decision_cols[i]:
                btn_type: Literal["primary", "secondary", "tertiary"] = "primary" if i == 0 else "secondary"
                clicked = st.button(
                    option, key=f"decide_{gate_id}_{option}", type=btn_type, use_container_width=True
                )
                if clicked:
                    decision = GateDecision(
                        gate_id=gate_id,
                        decision=option,
                        edits={},
                        comment="",
                        at=datetime.now(),
                    )
                    try:
                        from barthelona.domain import CommandKind, RunCommand

                        command = RunCommand(
                            run_id=run.id,
                            kind=CommandKind.RESUME,
                            decision=decision,
                        )
                        store.enqueue_command(command)
                        st.success(f"Decision '{option}' queued for gate {gate_id}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to queue decision: {e}")
                    return True

    return False


def _render_g1_spec(gate: Any, run: Any) -> None:
    """Render G1 spec approval payload."""
    payload = gate.payload

    # Show the project spec if available
    if "project_spec" in payload:
        spec = payload["project_spec"]
        st.write("**Project Specification**")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Slug:** {spec.get('slug', 'N/A')}")
            st.write(f"**Language:** {spec.get('request_lang', 'N/A')}")
            st.write(f"**Target:** {spec.get('target', {}).get('preset', 'N/A')}")
        with col2:
            st.write(f"**Modules:** {len(spec.get('modules', []))}")
            st.write(f"**Requirements:** {len(spec.get('requirements', []))}")
            st.write(f"**Constraints:** {len(spec.get('constraints', []))}")

        with st.expander("Full Specification (JSON)"):
            st.code(_format_payload(spec), language="json")

        with st.expander("Original Request"):
            st.text(spec.get("request_original", "N/A"))

        with st.expander("Summary (English)"):
            st.text(spec.get("summary_en", "N/A"))

    # Show any other artifacts
    for key, value in payload.items():
        if key != "project_spec":
            with st.expander(f"{key}"):
                if isinstance(value, (dict, list)):
                    st.code(_format_payload(value), language="json")
                else:
                    st.text(str(value))


def _render_g2_contracts(gate: Any, run: Any) -> None:
    """Render G2 contracts approval payload."""
    payload = gate.payload

    if "contracts_yaml" in payload:
        st.write("**Contracts (YAML)**")
        st.code(payload["contracts_yaml"], language="yaml")

    if "symbols" in payload:
        st.write("**Symbols**")
        symbols = payload["symbols"]
        if isinstance(symbols, list):
            st.dataframe(symbols, use_container_width=True)
        else:
            st.json(symbols)

    for key, value in payload.items():
        if key not in ("contracts_yaml", "symbols"):
            with st.expander(f"{key}"):
                if isinstance(value, (dict, list)):
                    st.code(_format_payload(value), language="json")
                else:
                    st.text(str(value))


def _render_verification_report(report: dict[str, Any]) -> None:
    """Render a verification report dict."""
    for level, result in report.items():
        if isinstance(result, dict):
            status = result.get("status", "unknown")
            icon = "✅" if status == "pass" else "❌" if status == "fail" else "⚪"
            st.write(f"{icon} **{level}**: {status}")
            if "details" in result:
                with st.expander(f"{level} details"):
                    st.json(result["details"])
        else:
            st.write(f"  {level}: {result}")


def _render_other_artifacts(payload: dict[str, Any], exclude_keys: set[str]) -> None:
    """Render payload keys not in exclude_keys."""
    for key, value in payload.items():
        if key not in exclude_keys:
            with st.expander(f"{key}"):
                if isinstance(value, (dict, list)):
                    st.code(_format_payload(value), language="json")
                else:
                    st.text(str(value))


def _render_g4_final(gate: Any, run: Any) -> None:
    """Render G4 final acceptance payload."""
    payload = gate.payload

    st.write("**Increment Artifacts**")

    if "workspace" in payload:
        st.write(f"**Workspace:** `{payload['workspace']}`")

    if "increment_files" in payload:
        st.write("**Files in this increment:**")
        files = payload["increment_files"]
        if isinstance(files, list):
            for f in files:
                st.code(f, language="text")
        else:
            st.json(files)

    if "verification_report" in payload:
        st.write("**Verification Report**")
        _render_verification_report(payload["verification_report"])

    _render_other_artifacts(payload, {"workspace", "increment_files", "verification_report"})


def page_approvals() -> None:
    st.header("✅ Approvals")

    store = open_store(Path("var/app.sqlite"))

    try:
        # Get all runs that are waiting at a gate
        runs = store.list_runs(RunStatus.WAITING_GATE)

        if not runs:
            st.info("No runs waiting for approval. Create a new run on the **New Request** page.")
            return

        st.write(f"Found **{len(runs)}** run(s) waiting at gates.")

        for run in runs:
            with st.expander(f"Run: `{run.id}` ({run.mode.value}) — {run.target.preset}", expanded=True):
                gates = store.pending_gates(run.id)

                if not gates:
                    st.warning("Run is WAITING_GATE but has no pending gates (data inconsistency)")
                    continue

                for gate in gates:
                    _render_gate_request(store, gate, run)

    except Exception as e:
        st.error(f"Error loading approvals: {e}")
    finally:
        store.close()

    # Auto-refresh
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh Now"):
        st.rerun()

    auto_refresh = st.sidebar.checkbox("Auto-refresh (2s)", value=False)
    if auto_refresh:
        st.sidebar.caption("Refreshing every 2 seconds...")
        import time

        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    page_approvals()
