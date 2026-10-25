"""The Package panel of the Live Run page: write a green run's repository files into its demos/ folder."""

from __future__ import annotations

import subprocess
from pathlib import Path

import streamlit as st

from barthelona.domain import Run, StopReason
from barthelona.domain.layout import RUNS_DIR
from barthelona.persistence import Store
from barthelona.scaffold import PackageError, package_run, target_folder

_SHA_LENGTH = 40


def current_commit() -> str:
    """The checked-out commit of this repository, or an empty string when it cannot be read."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git from PATH, fixed argv, no shell
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and len(sha) == _SHA_LENGTH else ""


def existing_files(folder: Path) -> list[str]:
    """Files already in *folder* (empty when it does not exist yet), as names relative to it."""
    if not folder.is_dir():
        return []
    return sorted(str(item.relative_to(folder)) for item in folder.rglob("*") if item.is_file())


def package_problem(run: Run, folder: Path | None, ref: str) -> str | None:
    """Why the button must stay disabled, or ``None`` when packaging may start."""
    if run.stop_reason is not StopReason.GREEN:
        return "Only a run that stopped green can be packaged."
    if folder is None:
        return "This run has no demos/ folder: start runs from New Request with a project folder."
    if len(ref) != _SHA_LENGTH:
        return "Enter the full 40-character commit sha of barthelona that the generated CI installs."
    if taken := existing_files(folder):
        return f"{folder} already has files ({', '.join(taken[:5])}); pick another project folder."
    return None


def render_package_panel(run: Run, store: Store) -> None:
    """Show the Package button for a green run, and list the files it wrote."""
    if run.stop_reason is not StopReason.GREEN:
        return
    st.subheader("Package")
    try:
        folder: Path | None = target_folder(run)
    except PackageError:
        folder = None
    st.write(
        f"Writes the source, golden tests, README, CI and release workflow into `{folder or '(no folder)'}`."
    )
    ref = st.text_input(
        "Barthelona commit sha for the generated CI", value=current_commit(), key=f"ref_{run.id}"
    )
    problem = package_problem(run, folder, ref.strip())
    if problem:
        st.info(problem)
    if st.button("Package into demos/", disabled=problem is not None, key=f"package_{run.id}"):
        try:
            written = package_run(store, RUNS_DIR, run.id, ref.strip())
        except (PackageError, OSError, ValueError) as exc:
            st.error(str(exc))
            return
        st.success(f"Wrote {len(written)} files into {folder}:")
        st.code("\n".join(written), language="text")
