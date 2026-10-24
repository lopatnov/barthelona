"""``barthelona meterless``: the honest state of a Meterless Runtime (Nightshift)."""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.console import Console

from barthelona.llm.meterless import DEFAULT_BASE_URL, parse_connect_link, probe

meterless_app = typer.Typer(help="Meterless Runtime (Nightshift) provider.", no_args_is_help=True)
_out = Console(soft_wrap=True, highlight=False)


@meterless_app.command("status")
def status(
    url: Annotated[
        str | None, typer.Option(help="Base URL or a connect link; default METERLESS_BASE_URL.")
    ] = None,
) -> None:
    """Probe GET /v1/models with METERLESS_RUNTIME_TOKEN: online, unauthorized or offline."""
    raw = url or os.environ.get("METERLESS_BASE_URL") or DEFAULT_BASE_URL
    token = os.environ.get("METERLESS_RUNTIME_TOKEN")
    link = parse_connect_link(raw)
    result = probe(link.base_url if link else raw, link.api_key if link else token)
    _out.print(f"{result.state} {result.base_url} {result.reason}".rstrip(), markup=False)
    for model in result.models:
        _out.print(f"  {model}", markup=False)
    if result.state != "online":
        raise typer.Exit(1)
