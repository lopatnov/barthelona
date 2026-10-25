"""``python -m barthelona worker``: the process that runs queued runs (docs/architecture.md §17)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from rich.console import Console

from barthelona.cli._activity import ACTIVITY_HELP, DEFAULT_ACTIVITY_LOG, activity_log
from barthelona.domain import EventKind, Run, RunEvent
from barthelona.domain.layout import REASONING_FILE, RUNS_DIR, run_dir
from barthelona.engine.graph import build_graph
from barthelona.engine.host import services_for, zetaris_facts
from barthelona.engine.worker import Worker
from barthelona.llm import CatalogError, Gateway, OpenAIChatBackend, load_catalog
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.hmem import HMem
from barthelona.llm.trace import ConsoleProgress, ConsoleTrace, ReasoningLog, TraceAll
from barthelona.llm.zetaris import ZetarisError
from barthelona.persistence import open_store
from barthelona.scaffold import PackageError, current_commit, package_run
from barthelona.world_model import DEFAULT_STORE, WorldModel

_err = Console(stderr=True, soft_wrap=True, highlight=False)


def _commit_or_fail() -> str:
    """The commit of barthelona the generated CI installs: this checkout's HEAD."""
    if not (sha := current_commit()):
        raise PackageError("cannot read this checkout's commit; start the worker inside the git repository")
    return sha


async def _run(
    db: Path,
    checkpoints: Path,
    runs: Path,
    catalog_path: Path,
    facts_sql: str | None,
    memory: Path,
    world_model: Path,
    poll: float,
    once: bool,
    trace: ReasoningLog | None,
    console: bool,
) -> None:
    catalog = load_catalog(catalog_path)
    facts = zetaris_facts(facts_sql) if facts_sql else None  # None: services_for uses the default facts
    backends = {"openai_chat": OpenAIChatBackend()}

    def gateway_for(run: Run) -> ModelGateway:
        run_log = ReasoningLog(run_dir(runs, run.id) / REASONING_FILE)  # what Live Run shows for this run
        traces = TraceAll(trace, run_log, ConsoleTrace() if console else None)
        console_progress = ConsoleProgress() if console else None

        def progress(message: str) -> None:  # Live Run shows it, so a long wait is not a silent one
            if console_progress is not None:
                console_progress(message)
            event = RunEvent(
                run_id=run.id,
                seq=store.next_seq(run.id),
                ts=datetime.now(UTC),
                kind=EventKind.LLM_CALL,
                payload={"status": message},
            )
            store.append_events([event])

        return Gateway(catalog, backends, profile=run.profile.value, trace=traces, progress=progress)

    store = open_store(db)
    hmem = HMem(memory)
    world = WorldModel(world_model)
    checkpoints.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoints)) as saver:
            worker = Worker(
                store,
                build_graph(
                    services_for(store, runs, gateway_for, facts, hmem, workspace_root=Path(), world=world),
                    saver,
                ),
                packager=lambda run_id: package_run(store, runs, run_id, _commit_or_fail()),
                world=world,
            )
            if once:
                await worker.recover()
                while await worker.step():
                    pass
            else:
                await worker.serve(poll)
    finally:
        world.close()
        hmem.close()
        store.close()


def worker_command(
    db: Annotated[Path, typer.Option(help="The app database.")] = Path("var/app.sqlite"),
    checkpoints: Annotated[Path, typer.Option(help="The LangGraph checkpoint database.")] = Path(
        "var/checkpoints.sqlite"
    ),
    runs: Annotated[Path, typer.Option(help="The per-run files folder.")] = RUNS_DIR,
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
    world_model: Annotated[
        Path,
        typer.Option("--world-model", help="World Model shared-state file a run records into (D-058)."),
    ] = DEFAULT_STORE,
    poll: Annotated[float, typer.Option(min=0.1, help="Seconds between polls when idle.")] = 1.0,
    once: Annotated[
        bool, typer.Option("--once", help="Run what is queued, then exit (for tests and CI).")
    ] = False,
    trace_reasoning: Annotated[
        str, typer.Option("--trace-reasoning", help=ACTIVITY_HELP)
    ] = DEFAULT_ACTIVITY_LOG,
    show_reasoning: Annotated[
        bool,
        typer.Option(
            "--show-reasoning/--no-show-reasoning",
            help="Print every model's name, thinking and answer (long ones cut short) to this terminal.",
        ),
    ] = True,
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
                world_model,
                poll,
                once,
                activity_log(trace_reasoning),
                show_reasoning,
            )
        )
    except (CatalogError, ZetarisError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    except KeyboardInterrupt:
        _err.print("worker stopped")
