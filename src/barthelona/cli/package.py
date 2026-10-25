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

from barthelona.domain import TestCase
from barthelona.engine.codegen import check_all
from barthelona.persistence import open_store
from barthelona.scaffold import PackageError, package_run
from barthelona.verification.asm_gate import find_nasm

_out = Console(soft_wrap=True, highlight=False)


def package_command(
    run_id: Annotated[str, typer.Argument(help="A run that stopped green.")],
    barthelona_ref: Annotated[
        str, typer.Option(help="Full commit sha of barthelona that the generated CI installs.")
    ],
    out: Annotated[
        Path | None,
        typer.Option(help="The folder that receives the project (default: the run's demos/ folder)."),
    ] = None,
    db: Annotated[Path, typer.Option("--db", help="The app database.")] = Path("var/app.sqlite"),
    runs: Annotated[Path, typer.Option("--runs", help="The per-run files folder.")] = Path("var/runs"),
    force: Annotated[bool, typer.Option(help="Overwrite files that already exist in --out.")] = False,
) -> None:
    """Write the repository files of a green single-module run: source, tests, README, CI and release."""
    try:
        with closing(open_store(db)) as store:
            written = package_run(store, runs, run_id, barthelona_ref, out, force)
    except PackageError as exc:
        raise typer.BadParameter(str(exc)) from exc
    for name in written:
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
