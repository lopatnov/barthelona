"""``barthelona chunked``: run one long task through the model gateway as Markovian chunks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from barthelona.llm import (
    CatalogError,
    Gateway,
    MarkovianConfig,
    MarkovianResult,
    OpenAIChatBackend,
    extract_code,
    load_catalog,
    run_markovian,
)

chunked_app = typer.Typer(
    help="Long tasks as bounded chunks with flat context (Markovian).", no_args_is_help=True
)
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)


def _table(result: MarkovianResult) -> Table:
    table = Table(
        "chunk", "served by", "tokens in", "tokens out", "chunk tokens", "ms", "marker", "carryover"
    )
    for chunk in result.chunks:
        table.add_row(
            str(chunk.index + 1),
            chunk.served_by,
            str(chunk.tokens_in),
            str(chunk.tokens_out),
            f"{chunk.tokens} ({chunk.token_source})",
            str(chunk.latency_ms),
            chunk.marker,
            chunk.carryover,
        )
    return table


@chunked_app.command("run")
def run(
    task: Annotated[str, typer.Argument(help="The task text, or @file to read it from a file.")],
    profile: Annotated[
        str, typer.Option(help="Catalog profile; 'meterless' routes via Nightshift.")
    ] = "meterless",
    role: Annotated[str, typer.Option(help="Catalog role whose chain answers each chunk.")] = "worker",
    out: Annotated[Path | None, typer.Option(help="Write the assembled output to this file.")] = None,
    code: Annotated[
        bool, typer.Option("--code", help="Write only the fenced code blocks (a source file), not the prose.")
    ] = False,
    chunk_tokens: Annotated[int, typer.Option(help="Tokens per chunk (engine range 1000-128000).")] = 8000,
    carryover_tokens: Annotated[int, typer.Option(help="Tokens of state carried between chunks.")] = 800,
    max_chunks: Annotated[int, typer.Option(help="Upper bound on chunks (1-32).")] = 24,
    catalog_path: Annotated[Path, typer.Option("--catalog", help="Model catalog.")] = Path(
        "config/models.yaml"
    ),
) -> None:
    """Run TASK in chunks, print per-chunk tokens and latency, and exit non-zero unless it completed."""
    try:
        catalog = load_catalog(catalog_path)
        config = MarkovianConfig(chunk_tokens, carryover_tokens, max_chunks)
    except (CatalogError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if task.startswith("@"):
        task = Path(task[1:]).read_text(encoding="utf-8")
    gateway = Gateway(catalog, {"openai_chat": OpenAIChatBackend()}, profile=profile)
    result = asyncio.run(run_markovian(gateway, role, task, config))
    text = extract_code(result.text) if code else result.text
    if out is not None:
        out.write_text(text + "\n", encoding="utf-8", newline="\n")
    else:
        _out.print(text, markup=False)
    _err.print(_table(result))
    for chunk in result.chunks:
        for reason in chunk.fallbacks:
            _err.print(f"chunk {chunk.index + 1} fell through: {reason}", markup=False)
    _err.print(
        f"stop_reason={result.stop_reason.value} chunks={len(result.chunks)} tokens_in={result.tokens_in} "
        f"tokens_out={result.tokens_out} peak_prompt={result.peak_tokens_in} status={result.status} "
        f"standard_cost={result.standard_cost} markovian_cost={result.markovian_cost} "
        f"efficiency={result.efficiency_percent:.1f}%",
        markup=False,
    )
    if result.stop_reason.value != "green":
        raise typer.Exit(1)
