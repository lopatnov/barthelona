"""``barthelona zetaris``: the honest state of a local Zetaris and read-only SQL against it."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from barthelona.llm.zetaris import DEFAULT_LIMIT, ZetarisConfig, ZetarisError, probe, run_sql
from barthelona.llm.zetaris_publish import (
    DATABASE,
    copy_into_container,
    default_sources,
    export_csv,
    register_missing,
)

zetaris_app = typer.Typer(help="Zetaris structured knowledge store (optional).", no_args_is_help=True)
_out = Console(soft_wrap=True, highlight=False)


@zetaris_app.command("status")
def status() -> None:
    """SELECT 1 over the REST API with ZETARIS_API_KEY: online, unauthorized, offline or unconfigured."""
    state, reason = probe(ZetarisConfig.from_env(os.environ))
    _out.print(f"{state} {reason}".rstrip(), markup=False)
    if state != "online":
        raise typer.Exit(1)


@zetaris_app.command("sql")
def sql(
    statement: Annotated[str, typer.Argument(help="One SELECT, SHOW, DESCRIBE or WITH statement.")],
    limit: Annotated[int, typer.Option(min=1, max=1000, help="Maximum rows.")] = DEFAULT_LIMIT,
) -> None:
    """Run one read-only statement and print the rows."""
    config = ZetarisConfig.from_env(os.environ)
    if config is None:
        _out.print("unconfigured: set ZETARIS_API_KEY", markup=False)
        raise typer.Exit(1)
    try:
        result = run_sql(config, statement, limit)
    except ZetarisError as exc:
        _out.print(str(exc), markup=False)
        raise typer.Exit(1) from exc
    _out.print(result.as_text(), markup=False)


@zetaris_app.command("publish")
def publish(
    container: Annotated[str, typer.Argument(help="Name or id of the Zetaris driver container (docker ps).")],
    runs_db: Annotated[Path, typer.Option(help="Run statistics database.")] = Path("var/runs.sqlite"),
    hmem_db: Annotated[Path, typer.Option(help="H-MEM database.")] = Path("var/hmem.sqlite"),
    out: Annotated[Path, typer.Option(help="Where the CSV files are written first.")] = Path(
        "var/zetaris_export"
    ),
) -> None:
    """Copy run history and H-MEM into Zetaris as tables (SQLite stays the store); safe to repeat."""
    config = ZetarisConfig.from_env(os.environ)
    if config is None:
        _out.print("unconfigured: set ZETARIS_API_KEY", markup=False)
        raise typer.Exit(1)
    try:
        sources = default_sources(runs_db, hmem_db)
        files = [export_csv(source, out) for source in sources]
        copy_into_container(files, container)
        created = register_missing(config, [source.zetaris_table for source in sources])
    except ZetarisError as exc:
        _out.print(str(exc), markup=False)
        raise typer.Exit(1) from exc
    _out.print(
        f"published {len(files)} tables to {DATABASE}; newly registered: {', '.join(created) or 'none'}",
        markup=False,
    )
