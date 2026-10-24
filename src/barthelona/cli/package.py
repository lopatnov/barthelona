"""``runs package`` and ``check``: turn a green single-module run into a repository, and re-check it anywhere.

`runs package` writes the files of one accepted run (source, golden tests, README, workflows) into a folder;
`check` is what the generated CI runs: NASM assembles the source and the emulator runs every golden test.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from barthelona.domain import ProjectSpec, StopReason, TestCase
from barthelona.engine.codegen import check_all
from barthelona.engine.graph import SOURCE_FILE
from barthelona.engine.host import REQUEST_FILE, SPEC_FILE, TESTS_FILE, run_dir
from barthelona.persistence import open_store
from barthelona.scaffold import UnsupportedCiTarget, render_project
from barthelona.verification.asm_gate import find_nasm

_out = Console(soft_wrap=True, highlight=False)


def package_command(
    run_id: Annotated[str, typer.Argument(help="A run that stopped green.")],
    out: Annotated[Path, typer.Option(help="The folder that receives the project.")],
    barthelona_ref: Annotated[
        str, typer.Option(help="Full commit sha of barthelona that the generated CI installs.")
    ],
    db: Annotated[Path, typer.Option("--db", help="The app database.")] = Path("var/app.sqlite"),
    runs: Annotated[Path, typer.Option("--runs", help="The per-run files folder.")] = Path("var/runs"),
    force: Annotated[bool, typer.Option(help="Overwrite files that already exist in --out.")] = False,
) -> None:
    """Write the repository files of a green single-module run: source, tests, README, CI and release."""
    with closing(open_store(db)) as store:
        run = store.get_run(run_id)
        calls = store.llm_calls(run_id)
    if run.stop_reason is not StopReason.GREEN:
        raise typer.BadParameter(f"run {run_id} did not stop green ({run.stop_reason}); nothing to package")
    folder = run_dir(runs, run_id)
    spec = ProjectSpec.model_validate_json((folder / SPEC_FILE).read_text(encoding="utf-8"))
    cases = [TestCase.model_validate(item) for item in json.loads((folder / TESTS_FILE).read_text("utf-8"))]
    try:
        files = render_project(
            run,
            spec,
            cases,
            (folder / SOURCE_FILE).read_text(encoding="utf-8"),
            (folder / REQUEST_FILE).read_text(encoding="utf-8"),
            calls,
            barthelona_ref,
        )
    except UnsupportedCiTarget as exc:
        raise typer.BadParameter(str(exc)) from exc
    taken = [name for name in files if (out / name).exists() and not force]
    if taken:
        raise typer.BadParameter(f"{out} already has {', '.join(taken)}; use --force to overwrite")
    for name, text in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        _out.print(name, markup=False)


def check_command(
    source: Annotated[Path, typer.Argument(help="The NASM source to assemble and run.")],
    tests: Annotated[Path, typer.Option(help="The golden tests (a JSON list of test cases).")] = Path(
        "tests/golden.json"
    ),
) -> None:
    """Assemble *source* with NASM and run every golden test in the emulator; exit 1 unless all pass."""
    cases = [TestCase.model_validate(item) for item in json.loads(tests.read_text(encoding="utf-8"))]
    verdict = check_all(source.read_text(encoding="utf-8"), cases, find_nasm(None))
    for error in verdict.errors:
        _out.print(error, markup=False)
    _out.print(f"{source}: {verdict.status} ({len(cases)} tests)", markup=False)
    raise typer.Exit(0 if verdict.status == "pass" else 1)
