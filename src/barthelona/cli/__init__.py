"""Command-line interface (Typer). Commands land with their phase (docs/roadmap.md)."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

import barthelona
from barthelona.domain import DOCUMENTS

app = typer.Typer(
    name="barthelona",
    help="Create or edit multi-file assembly projects from a natural-language request.",
    no_args_is_help=True,
    add_completion=False,
)
_out = Console(soft_wrap=True, highlight=False)


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


def main() -> None:
    app()
