"""New Request page: create a new run from a natural-language prompt.

Phase 1a fields:
- New project checkbox: create (a typed project name) or edit (a pick from demos/)
- Dialect/preset picker (built-in list)
- Project under demos/ the result belongs to
- Prompt textarea (Russian/English/Ukrainian)
- Profile: meterless / local-only / hybrid / cloud
- Budget controls (wall time, tokens, optional USD cap)
- Collect training data checkbox (D-036)
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from barthelona.domain import (
    DEFAULT_TOKENS,
    DEFAULT_WALL_S,
    DEMOS_DIR,
    CompositionLevel,
    Profile,
    Run,
    RunBudget,
    RunMode,
    project_workspace,
)
from barthelona.domain.layout import REQUEST_FILE, RUNS_DIR, run_dir
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store


def _demo_folders() -> list[str]:
    """The subfolders of demos/ a run can belong to, sorted; empty when the directory is missing."""
    root = Path(DEMOS_DIR)
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir()) if root.is_dir() else []


def _project_field(new_project: bool) -> str:
    """The demos/ project the run belongs to: a typed name for a new one, a pick from the list otherwise."""
    if new_project:
        name = st.text_input(
            "Project",
            placeholder="my-demo",
            help="The demos/ subfolder for the new project: lowercase letters, digits and dashes.",
        )
        return name.strip()
    folders = _demo_folders()
    if not folders:
        st.info("There is no project in demos/ yet: tick 'New project' to create one.")
        return ""
    return st.selectbox("Project", folders, help="The existing demos/ project this run edits.")


def _form_problem(prompt: str, folder: str) -> str | None:
    """What is wrong with the submitted form, or None when it can become a run."""
    if not prompt.strip():
        return "Prompt cannot be empty."
    try:
        project_workspace(folder)
    except ValueError as exc:
        return f"Folder name: {exc}"
    return None


def _limits_fields() -> tuple[float, int, float, int]:
    """The run limits, collapsed: every run is bounded (invariant 6), but nobody has to fill these in."""
    with st.expander("Limits (optional: the defaults shown here apply if you leave them as they are)"):
        st.caption(
            "A run stops at the first limit it reaches. Money is metered, but capped only if you set a cap."
        )
        col_time, col_tokens, col_usd = st.columns(3)
        with col_time:
            wall_s = st.number_input(
                "Wall time (seconds)", min_value=10.0, max_value=86400.0, value=DEFAULT_WALL_S, step=60.0
            )
        with col_tokens:
            tokens = st.number_input(
                "Token limit", min_value=1000, max_value=10_000_000, value=DEFAULT_TOKENS, step=10_000
            )
        with col_usd:
            usd = st.number_input(
                "USD cap (0 = none)", min_value=0.0, max_value=1000.0, value=0.0, step=0.1, format="%.2f"
            )
        max_sprints = st.number_input("Max sprints", min_value=1, max_value=50, value=10, step=1)
    return float(wall_s), int(tokens), float(usd), int(max_sprints)


def page_new_request() -> None:
    st.header("🆕 New Request")

    presets = builtin_presets()

    # Outside the form: a form only reruns on submit, and the Project field depends on this box.
    new_project = st.checkbox(
        "New project", value=True, help="Ticked: create a new project. Unticked: edit one."
    )
    mode = RunMode.CREATE if new_project else RunMode.EDIT

    with st.form("new_request_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
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
                    Profile.METERLESS: "⚡ Meterless (Nightshift model routing, Zetaris facts)",
                    Profile.LOCAL_ONLY: "🏠 Local only (LM Studio / Ollama)",
                    Profile.HYBRID: "🔀 Hybrid (cloud with local fallback)",
                    Profile.CLOUD: "☁️ Cloud (Anthropic, OpenAI, Gemini, DeepSeek)",
                }[p],
                horizontal=False,
            )

        st.divider()

        folder = _project_field(new_project)

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

        wall_s, tokens, usd, max_sprints = _limits_fields()

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
        if problem := _form_problem(prompt, folder):
            st.error(problem)
            return

        # Create the run
        run_id = f"run_{uuid4().hex[:12]}"

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
            workspace=project_workspace(folder),
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

            # The prompt goes where the worker reads it: same folder and file name as `runs submit` uses.
            req_path = run_dir(RUNS_DIR, run.id) / REQUEST_FILE
            req_path.parent.mkdir(parents=True, exist_ok=True)
            req_path.write_text(prompt.strip(), encoding="utf-8", newline="\n")

            store.close()

            st.success(f"Run created: `{run_id}`")
            st.info(f"Project folder: `{run.workspace}`")
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
