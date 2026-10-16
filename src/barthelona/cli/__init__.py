"""Command-line interface (Typer). Commands land with their phase (docs/roadmap.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import barthelona
from barthelona.domain import DOCUMENTS, Verdict
from barthelona.training import DatasetError, DatasetReader, TrainingDataSettings, count_verdicts

app = typer.Typer(
    name="barthelona",
    help="Create or edit multi-file assembly projects from a natural-language request.",
    no_args_is_help=True,
    add_completion=False,
)
training_app = typer.Typer(help="The local training dataset (opt-in, D-036).", no_args_is_help=True)
app.add_typer(training_app, name="training")
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)


@app.command()
def version() -> None:
    """Print the barthelona version."""
    _out.print(barthelona.__version__)


@app.command()
def schema(
    model: Annotated[str | None, typer.Argument(help="Document name, e.g. TopologyRequest.")] = None,
) -> None:
    """Print the JSON schema of a domain document, or list the documents."""
    if model is None:
        for name in sorted(DOCUMENTS):
            _out.print(name)
        return
    cls = DOCUMENTS.get(model)
    if cls is None:
        raise typer.BadParameter(f"unknown document {model!r}; run without an argument to list them")
    _out.print(json.dumps(cls.model_json_schema(), indent=2, sort_keys=True), markup=False)


@app.command()
def probe(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the lock file (default: config/toolchains.lock.json).",
        ),
    ] = Path("config/toolchains.lock.json"),
) -> None:
    """Probe the bart-tc container and write config/toolchains.lock.json.

    Requires Windows with WSL and a running bart-tc Docker container.
    """
    from barthelona.executors import WslUnavailableError
    from barthelona.executors.wsl import WslExecutor
    from barthelona.toolchains import run_probe, write_lock_file

    try:
        executor = WslExecutor()
    except WslUnavailableError as exc:
        _err.print(f"[bold red]probe unavailable:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    _out.print("Probing bart-tc container…")
    try:
        with executor:
            lock = run_probe(executor)
    except Exception as exc:  # noqa: BLE001  -- surface all probe errors to the user as a single message
        _err.print(f"[bold red]probe failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    write_lock_file(lock, output)
    _out.print(f"Wrote {output}")
    _out.print(f"  toolchain image: {lock.toolchain_image_digest or '(unknown)'}")
    _out.print(f"  runner image:    {lock.runner_image_digest or '(unknown)'}")
    for name, info in lock.tools.items():
        _out.print(f"  {name}: {info.version} at {info.path}")


@training_app.command("status")
def training_status() -> None:
    """Show whether training data is collected, where, and how many samples each verdict has."""
    settings = TrainingDataSettings()
    state = "enabled" if settings.enabled else "disabled (set BARTHELONA_TRAINING_DATA_ENABLED=1)"
    _out.print(f"collection: {state}", markup=False)
    _out.print(f"directory: {settings.directory}", markup=False)
    try:
        verdicts = count_verdicts(DatasetReader(settings.directory).samples())
    except DatasetError as error:
        _err.print(str(error), markup=False)
        raise typer.Exit(1) from error
    for verdict in Verdict:
        _out.print(f"{verdict.value}: {verdicts[verdict]}", markup=False)


def main() -> None:
    app()
