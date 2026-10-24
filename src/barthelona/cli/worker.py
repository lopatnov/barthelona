"""``python -m barthelona worker``: the process that runs queued runs (docs/architecture.md §17)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.console import Console

from barthelona.engine.graph import build_graph
from barthelona.engine.preflight import preflight_for
from barthelona.engine.worker import Worker
from barthelona.persistence import open_store

_err = Console(stderr=True, soft_wrap=True, highlight=False)


async def _run(db: Path, checkpoints: Path, poll: float, once: bool) -> None:
    store = open_store(db)
    checkpoints.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoints)) as saver:
            worker = Worker(store, build_graph(preflight_for(store), saver))
            if once:
                await worker.recover()
                while await worker.step():
                    pass
            else:
                await worker.serve(poll)
    finally:
        store.close()


def worker_command(
    db: Annotated[Path, typer.Option(help="The app database.")] = Path("var/app.sqlite"),
    checkpoints: Annotated[Path, typer.Option(help="The LangGraph checkpoint database.")] = Path(
        "var/checkpoints.sqlite"
    ),
    poll: Annotated[float, typer.Option(min=0.1, help="Seconds between polls when idle.")] = 1.0,
    once: Annotated[
        bool, typer.Option("--once", help="Run what is queued, then exit (for tests and CI).")
    ] = False,
) -> None:
    """Claim queued runs, run them to their next human gate and continue them when the UI resumes them."""
    try:
        asyncio.run(_run(db, checkpoints, poll, once))
    except KeyboardInterrupt:
        _err.print("worker stopped")
