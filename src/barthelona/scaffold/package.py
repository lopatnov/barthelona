"""Write the repository files of a green run into a folder: ``runs package`` and the UI button."""

from __future__ import annotations

import json
from pathlib import Path

from barthelona.domain import DEMOS_DIR, ProjectSpec, Run, StopReason, TestCase
from barthelona.engine.graph import SOURCE_FILE
from barthelona.engine.host import REQUEST_FILE, SPEC_FILE, TESTS_FILE, run_dir
from barthelona.persistence import Store
from barthelona.scaffold.ci import UnsupportedCiTarget
from barthelona.scaffold.project import render_project


class PackageError(ValueError):
    """The run cannot be packaged; the message says why and what to do."""


def target_folder(run: Run, out: Path | None = None) -> Path:
    """Where the project goes: *out*, or the run's ``demos/`` folder."""
    if out is not None:
        return out
    if not run.workspace.startswith(f"{DEMOS_DIR}/"):
        raise PackageError(f"run {run.id} has no demos/ folder (workspace {run.workspace}); pass --out")
    return Path(run.workspace)


def package_run(
    store: Store,
    runs_dir: Path,
    run_id: str,
    barthelona_ref: str,
    out: Path | None = None,
    force: bool = False,
) -> list[str]:
    """Render and write the project of a green run; return the written file names."""
    run = store.get_run(run_id)
    target_dir = target_folder(run, out)
    if run.stop_reason is not StopReason.GREEN:
        raise PackageError(f"run {run_id} did not stop green ({run.stop_reason}); nothing to package")
    folder = run_dir(runs_dir, run_id)
    spec = ProjectSpec.model_validate_json((folder / SPEC_FILE).read_text(encoding="utf-8"))
    cases = [TestCase.model_validate(item) for item in json.loads((folder / TESTS_FILE).read_text("utf-8"))]
    try:
        files = render_project(
            run,
            spec,
            cases,
            (folder / SOURCE_FILE).read_text(encoding="utf-8"),
            (folder / REQUEST_FILE).read_text(encoding="utf-8"),
            store.llm_calls(run_id),
            barthelona_ref,
        )
    except UnsupportedCiTarget as exc:
        raise PackageError(str(exc)) from exc
    taken = [name for name in files if (target_dir / name).exists() and not force]
    if taken:
        raise PackageError(f"{target_dir} already has {', '.join(taken)}; use --force to overwrite")
    for name, text in files.items():
        target = target_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return list(files)
