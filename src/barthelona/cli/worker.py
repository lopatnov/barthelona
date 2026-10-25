"""``python -m barthelona worker``: the process that runs queued runs (docs/architecture.md §17)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.console import Console

from barthelona.cli._activity import ACTIVITY_HELP, DEFAULT_ACTIVITY_LOG, activity_log
from barthelona.domain import Run
from barthelona.engine.graph import build_graph
from barthelona.engine.host import services_for, zetaris_facts
from barthelona.engine.worker import Worker
from barthelona.llm import CatalogError, Gateway, OpenAIChatBackend, load_catalog
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.hmem import HMem
from barthelona.llm.trace import ReasoningLog
from barthelona.llm.zetaris import ZetarisError
from barthelona.persistence import open_store

_err = Console(stderr=True, soft_wrap=True, highlight=False)


async def _run(
    db: Path,
    checkpoints: Path,
    runs: Path,
    catalog_path: Path,
    facts_sql: str | None,
    memory: Path,
    poll: float,
    once: bool,
    trace: ReasoningLog | None,
) -> None:
    catalog = load_catalog(catalog_path)
    facts = zetaris_facts(facts_sql) if facts_sql else None  # None: services_for uses the default facts
    backends = {"openai_chat": OpenAIChatBackend()}

    def gateway_for(run: Run) -> ModelGateway:
        return Gateway(catalog, backends, profile=run.profile.value, trace=trace)

    store = open_store(db)
    hmem = HMem(memory)
    checkpoints.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoints)) as saver:
            worker = Worker(store, build_graph(services_for(store, runs, gateway_for, facts, hmem), saver))
            if once:
                await worker.recover()
                while await worker.step():
                    pass
            else:
                await worker.serve(poll)
    finally:
        hmem.close()
        store.close()


def worker_command(
    db: Annotated[Path, typer.Option(help="The app database.")] = Path("var/app.sqlite"),
    checkpoints: Annotated[Path, typer.Option(help="The LangGraph checkpoint database.")] = Path(
        "var/checkpoints.sqlite"
    ),
    runs: Annotated[Path, typer.Option(help="The per-run files folder.")] = Path("var/runs"),
    catalog_path: Annotated[Path, typer.Option("--catalog", help="Model catalog.")] = Path(
        "config/models.yaml"
    ),
    facts_sql: Annotated[
        str | None,
        typer.Option(
            "--facts-sql",
            help="One read-only Zetaris statement for the spec and test-author prompts "
            "(default with ZETARIS_API_KEY: the Barthelona knowledge tables).",
        ),
    ] = None,
    memory: Annotated[
        Path | None,
        typer.Option(help="H-MEM store recalled in every chunk (default: hmem.sqlite next to --db)."),
    ] = None,
    poll: Annotated[float, typer.Option(min=0.1, help="Seconds between polls when idle.")] = 1.0,
    once: Annotated[
        bool, typer.Option("--once", help="Run what is queued, then exit (for tests and CI).")
    ] = False,
    trace_reasoning: Annotated[
        str, typer.Option("--trace-reasoning", help=ACTIVITY_HELP)
    ] = DEFAULT_ACTIVITY_LOG,
) -> None:
    """Claim queued runs, run them to their next human gate and continue them when the UI resumes them."""
    try:
        asyncio.run(
            _run(
                db,
                checkpoints,
                runs,
                catalog_path,
                facts_sql,
                memory or db.parent / "hmem.sqlite",
                poll,
                once,
                activity_log(trace_reasoning),
            )
        )
    except (CatalogError, ZetarisError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    except KeyboardInterrupt:
        _err.print("worker stopped")
