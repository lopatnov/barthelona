"""Command-line interface (Typer). Commands land with their phase (docs/roadmap.md)."""

from __future__ import annotations

import json
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
