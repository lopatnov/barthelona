"""``barthelona meterless``: the honest state of a Meterless Runtime (Nightshift)."""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.console import Console

from barthelona.llm.meterless import DEFAULT_BASE_URL, offer, parse_connect_link, probe, route_probe

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


@meterless_app.command("models")
def models(
    url: Annotated[
        str | None, typer.Option(help="Base URL or a connect link; default METERLESS_BASE_URL.")
    ] = None,
    lanes: Annotated[
        bool,
        typer.Option(
            "--lanes",
            help="Ask every routing mode once (a few tokens each) and print the model that answered.",
        ),
    ] = False,
    tier: Annotated[
        str | None, typer.Option("--tier", help="Only models the runtime grades at this tier (A, B or C).")
    ] = None,
    kind: Annotated[str | None, typer.Option("--kind", help="Only cloud or local models.")] = None,
    free: Annotated[bool, typer.Option("--free", help="Only models the runtime prices at zero.")] = False,
) -> None:
    """List the routing modes and the concrete models that can be called directly (GET /v1/models)."""
    raw = url or os.environ.get("METERLESS_BASE_URL") or DEFAULT_BASE_URL
    token = os.environ.get("METERLESS_RUNTIME_TOKEN")
    link = parse_connect_link(raw)
    base, key = (link.base_url, link.api_key) if link else (raw, token)
    listed = offer(base, key)
    if not listed.routes and not listed.served:
        _out.print(f"no models: {listed.reason}", markup=False)
        raise typer.Exit(1)
    _out.print(f"routing modes ({len(listed.routes)})", markup=False)
    for route in listed.routes:
        _out.print(f"  {route.id:24} {route.availability:10} {route.description}", markup=False)
    wanted = [
        model
        for model in listed.served
        if (not tier or model.tier == tier.upper())
        and (not kind or model.kind == kind.lower())
        and (not free or model.price_in == 0)
    ]
    _out.print(
        f"models that can be called directly ({len(wanted)} of {len(listed.served)}): "
        "kind, tier, context, USD per 1M input/output",
        markup=False,
    )
    for model in sorted(wanted, key=lambda entry: (entry.kind, entry.tier, entry.id)):
        context = str(model.context) if model.context else "-"
        price = "-" if model.price_in is None else f"{model.price_in:g}/{model.price_out or 0:g}"
        _out.print(f"  {model.id:52} {model.kind:5} {model.tier:3} {context:>7} {price:>11}", markup=False)
    if not lanes:
        return
    _out.print("what each mode answers with now (one tiny call each)", markup=False)
    for route in listed.routes:
        answered = route_probe(base, key, route.id)
        told = answered.model or answered.reason or f"HTTP {answered.status}"
        _out.print(f"  {route.id:24} -> {told[:160]}", markup=False)
