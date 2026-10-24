"""New Request page: create a new run from a natural-language prompt.

Phase 1a fields:
- Mode: create / edit
- Dialect/preset picker (built-in list)
- Prompt textarea (Russian/English/Ukrainian)
- Profile: meterless / local-only / hybrid / cloud
- Budget controls (wall time, tokens, optional USD cap)
- Collect training data checkbox (D-036)
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from barthelona.domain import CompositionLevel, Profile, Run, RunBudget, RunMode
from barthelona.domain.presets import builtin_presets
from barthelona.engine.host import REQUEST_FILE, run_dir
from barthelona.persistence import open_store


def page_new_request() -> None:
    st.header("🆕 New Request")

    presets = builtin_presets()

    with st.form("new_request_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            mode = st.radio(
                "Mode",
                [RunMode.CREATE, RunMode.EDIT],
                format_func=lambda m: (
                    "🆕 Create new project" if m == RunMode.CREATE else "✏️ Edit existing project"
                ),
                horizontal=True,
            )

            preset = st.selectbox(
                "Target Preset",
                presets,
                format_func=lambda p: f"{p.preset} ({p.dialect.value}, {p.arch.value}, {p.os.value})",
            )

        with col2:
            profile = st.radio(
                "Model Profile",
                [Profile.METERLESS, Profile.LOCAL_ONLY, Profile.HYBRID, Profile.CLOUD],
                format_func=lambda p: {
                    Profile.METERLESS: "⚡ Meterless (Nightshift routes to free Nemotron lanes)",
                    Profile.LOCAL_ONLY: "🏠 Local only (LM Studio / Ollama)",
                    Profile.HYBRID: "🔀 Hybrid (cloud with local fallback)",
                    Profile.CLOUD: "☁️ Cloud (Anthropic, OpenAI, Gemini, DeepSeek)",
                }[p],
                horizontal=False,
            )

        st.divider()

        prompt = st.text_area(
            "Prompt",
            placeholder="Describe the assembly program you want... (Russian, English, or Ukrainian)",
            height=200,
            help=(
                "Describe the goal in natural language. "
                "The Meta-Agentic Scrum engine will turn this into a spec, contracts, and code."
            ),
        )

        st.divider()

        # Budget controls
        st.subheader("Budget")
        col3, col4, col5 = st.columns(3)
        with col3:
            wall_s = st.number_input("Wall time (seconds)", min_value=10, max_value=3600, value=300, step=10)
        with col4:
            tokens = st.number_input(
                "Token budget", min_value=1000, max_value=1000000, value=50000, step=1000
            )
        with col5:
            usd = st.number_input(
                "USD cap (optional)", min_value=0.0, max_value=1000.0, value=0.0, step=0.1, format="%.2f"
            )

        max_sprints = st.number_input("Max sprints", min_value=1, max_value=50, value=10, step=1)

        col6, col7 = st.columns(2)
        with col6:
            cloud_allowed = st.checkbox(
                "Allow cloud providers",
                value=(profile != Profile.LOCAL_ONLY),
                disabled=(profile == Profile.LOCAL_ONLY),
                help="Local-only profile cannot use cloud providers",
            )
        with col7:
            collect_training = st.checkbox(
                "Collect training data (D-036)",
                value=False,
                help="Record code-producing attempts after the ladder for local-model training export",
            )

        submitted = st.form_submit_button("🚀 Create Run", type="primary", use_container_width=True)

    if submitted:
        if not prompt.strip():
            st.error("Prompt cannot be empty.")
            return

        # Create the run
        run_id = f"run_{uuid4().hex[:12]}"
        workspace = f"workspaces/{run_id}"

        budget = RunBudget(
            wall_s=float(wall_s),
            tokens=int(tokens),
            usd=usd if usd > 0 else None,
            max_sprints=int(max_sprints),
            cloud_allowed=cloud_allowed,
        )

        run = Run(
            id=run_id,
            mode=mode,
            workspace=workspace,
            target=preset,
            profile=profile,
            policy_version="v1",  # Will be loaded from policies/v1/ later
            budget=budget,
            composition_level=CompositionLevel.L0,
            collect_training_data=collect_training,
        )

        try:
            store = open_store(Path("var/app.sqlite"))
            store.create_run(run)

            # Persist the prompt where the worker expects it (invariant 8 + host.load_request)
            runs_dir = Path("var/runs")
            req_path = run_dir(runs_dir, run.id) / REQUEST_FILE
            req_path.parent.mkdir(parents=True, exist_ok=True)
            req_path.write_text(prompt.strip(), encoding="utf-8", newline="\n")

            store.close()

            st.success(f"Run created: `{run_id}`")
            st.info(f"Workspace: `{workspace}`")
            st.info("Switch to the **Approvals** page to review gates, or **Live Run** to watch execution.")

            # Offer to switch pages - use query params or callback
            if st.button("Go to Approvals →", key="goto_approvals"):
                st.query_params["page"] = "Approvals"
                st.rerun()

        except Exception as e:
            st.error(f"Failed to create run: {e}")


if __name__ == "__main__":
    # For direct testing
    page_new_request()
