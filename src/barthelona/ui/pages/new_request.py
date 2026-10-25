"""New Request page: create a new run from a natural-language prompt.

Phase 1a fields:
- New project checkbox: checked creates a project in a new demos/ folder, unchecked edits an existing one
- Dialect/preset picker (built-in list)
- Project: a new folder name (checked) or the list of existing demos/ folders (unchecked)
- Prompt textarea (Russian/English/Ukrainian)
- Profile: meterless / local-only / hybrid / cloud
- Budget controls (wall time, tokens, optional USD cap)
- Approve checkpoints automatically (on by default)
- Write the project into demos/ when the run is green (off by default)
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
from barthelona.ui.bounds import REAL_BOUNDS
from barthelona.ui.navigation import open_page

_PROFILE_NOTE = (
    "Nightshift (Meterless) is the model router: every request goes to one of its lanes (auto, deep, fast). "
    "Zetaris works with every profile: with ZETARIS_API_KEY set, its assembler facts (syscalls, ABI) are put "
    "into the prompts."
)


def _demo_folders() -> list[str]:
    """The subfolders of demos/ a run can belong to, sorted; empty when the directory is missing."""
    root = Path(DEMOS_DIR)
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir()) if root.is_dir() else []


def _folder_fields(new_project: bool) -> str:
    """The demos/ folder: the name typed in for a new project (not yet validated), or the existing pick."""
    if new_project:
        name = st.text_input(
            "Project",
            placeholder="my-demo",
            help="The demos/ folder the new project goes to: lowercase letters, digits and dashes.",
        )
        return name.strip()
    existing = _demo_folders()
    if not existing:
        st.warning("demos/ has no projects yet: tick **New project**.")
        return ""
    return st.selectbox("Project", existing, help="The existing demos/ folder to edit.")


def _form_problem(prompt: str, folder: str) -> str | None:
    """What is wrong with the submitted form, or None when it can become a run."""
    if not prompt.strip():
        return "Prompt cannot be empty."
    try:
        project_workspace(folder)
    except ValueError as exc:
        return f"Folder name: {exc}"
    return None


def _limits_fields() -> tuple[float, int, float]:
    """The run limits, collapsed: every run is bounded (invariant 6), but nobody has to fill these in."""
    with st.expander("Limits (optional: the defaults shown here apply if you leave them as they are)"):
        st.caption(
            "No need to fill these in: a run may use up to 4 hours of work and 400,000 tokens. It stops at "
            "the first limit it reaches, and a run that stopped on a limit can be continued from Live Run. "
            "Money is metered, but capped only if you set a cap."
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
        st.caption(REAL_BOUNDS)
    return float(wall_s), int(tokens), float(usd)


def page_new_request() -> None:
    st.header("🆕 New Request")

    presets = builtin_presets()

    # Outside the form: a form only reacts on submit, and this choice changes which fields it shows.
    new_project = st.checkbox(
        "New project", value=True, help="Unticked: edit a project that already exists in demos/."
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
                    Profile.METERLESS: "⚡ Meterless (Nightshift)",
                    Profile.LOCAL_ONLY: "🏠 Local only (LM Studio / Ollama)",
                    Profile.HYBRID: "🔀 Hybrid (cloud with local fallback)",
                    Profile.CLOUD: "☁️ Cloud (Anthropic, OpenAI, Gemini, DeepSeek)",
                }[p],
                horizontal=False,
            )
            st.caption(_PROFILE_NOTE)

        st.divider()

        folder = _folder_fields(new_project)

        prompt = st.text_area(
            "Prompt",
            placeholder="Describe the assembly program you want... (Russian, English, or Ukrainian)",
            height=200,
            help=(
                "Describe the goal in natural language. "
                "The Meta-Agentic Scrum engine will turn this into a spec, contracts, and code."
            ),
        )

        st.markdown("**After you click Create Run**")
        auto_approve = st.checkbox(
            "Approve checkpoints automatically",
            value=True,
            help=(
                "G1 (specification and tests) and G4 (the finished code) are approved by the worker "
                "and logged as automatic. Untick to read and approve them yourself on the Approvals page. "
                "The assembler and the emulator still decide whether the code is accepted."
            ),
        )

        auto_package = st.checkbox(
            "Write the project into demos/ when the run is green",
            value=False,
            help=(
                "Tick to have the worker package the source, tests, README and CI into the project folder "
                "as soon as the run is green. Unticked, use the Package button on Live Run."
            ),
        )

        st.divider()

        wall_s, tokens, usd = _limits_fields()

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
            auto_approve=auto_approve,
            auto_package=auto_package,
        )

        try:
            store = open_store(Path("var/app.sqlite"))
            store.create_run(run)

            # The prompt goes where the worker reads it: same folder and file name as `runs submit` uses.
            req_path = run_dir(RUNS_DIR, run.id) / REQUEST_FILE
            req_path.parent.mkdir(parents=True, exist_ok=True)
            req_path.write_text(prompt.strip(), encoding="utf-8", newline="\n")

            store.close()

        except Exception as e:
            st.error(f"Failed to create run: {e}")
            return

        st.session_state["active_run_id"] = run_id  # Live Run opens on this run
        st.success(f"Run created: `{run_id}`. Project folder: `{run.workspace}`")
        open_page("live_run")


if __name__ == "__main__":
    # For direct testing
    page_new_request()
