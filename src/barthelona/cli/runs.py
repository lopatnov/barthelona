"""``python -m barthelona runs``: queue a run, watch it and answer its gates without the UI.

It writes the same rows and files as the UI (a run, `request.txt`, resume commands), so the worker cannot tell
the difference (invariant 8: only SQLite connects them).
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console

from barthelona.cli.package import package_command
from barthelona.domain import (
    DEFAULT_TOKENS,
    DEFAULT_WALL_S,
    CommandKind,
    GateDecision,
    Profile,
    Run,
    RunBudget,
    RunCommand,
    RunMode,
    project_workspace,
)
from barthelona.domain.layout import REQUEST_FILE, RUNS_DIR, SOURCE_FILE, run_dir
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store

runs_app = typer.Typer(help="Queue runs and answer their gates (the UI does the same).", no_args_is_help=True)
_out = Console(soft_wrap=True, highlight=False)

runs_app.command("package")(package_command)

_DB = typer.Option("--db", help="The app database.")
_RUNS = typer.Option("--runs", help="The per-run files folder.")
_DEFAULT_DB = Path("var/app.sqlite")


@runs_app.command("submit")
def submit(
    request: Annotated[str, typer.Argument(help="The request text, or @file to read it from a file.")],
    profile: Annotated[Profile, typer.Option(help="Catalog profile the run uses.")] = Profile.METERLESS,
    preset: Annotated[str, typer.Option(help="Target preset.")] = "linux-x64-nasm-static",
    wall_s: Annotated[float, typer.Option(min=1, help="Wall-clock limit in seconds.")] = DEFAULT_WALL_S,
    tokens: Annotated[int, typer.Option(min=1, help="Token limit.")] = DEFAULT_TOKENS,
    project: Annotated[
        str | None, typer.Option(help="Name of the demos/ subfolder the project is for (a lowercase slug).")
    ] = None,
    auto_approve: Annotated[
        bool,
        typer.Option(
            "--auto-approve/--no-auto-approve",
            help="The worker approves G1 and G4 itself (default); --no-auto-approve waits for you.",
        ),
    ] = True,
    package: Annotated[
        bool,
        typer.Option(
            "--package/--no-package",
            help="The worker writes the project into demos/ when the run is green (default).",
        ),
    ] = True,
    db: Annotated[Path, _DB] = _DEFAULT_DB,
    runs: Annotated[Path, _RUNS] = RUNS_DIR,
) -> None:
    """Queue a create-mode run; the worker picks it up and parks it at gate G1."""
    target = next((p for p in builtin_presets() if p.preset == preset), None)
    if target is None:
        known = ", ".join(p.preset for p in builtin_presets())
        raise typer.BadParameter(f"unknown preset {preset!r}; choose one of: {known}")
    try:
        workspace = project_workspace(project) if project else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    text = Path(request[1:]).read_text(encoding="utf-8") if request.startswith("@") else request
    run_id = f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    run = Run(
        id=run_id,
        mode=RunMode.CREATE,
        workspace=workspace or f"workspaces/{run_id}",
        target=target,
        profile=profile,
        policy_version="v1",
        budget=RunBudget(wall_s=wall_s, tokens=tokens, cloud_allowed=profile is not Profile.LOCAL_ONLY),
        auto_approve=auto_approve,
        auto_package=package,
    )
    folder = run_dir(runs, run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / REQUEST_FILE).write_text(text, encoding="utf-8", newline="\n")
    with closing(open_store(db)) as store:
        store.create_run(run)
    _out.print(run_id, markup=False)


@runs_app.command("status")
def status(
    run_id: Annotated[str | None, typer.Argument(help="A run id; without it, every run is listed.")] = None,
    db: Annotated[Path, _DB] = _DEFAULT_DB,
    runs: Annotated[Path, _RUNS] = RUNS_DIR,
) -> None:
    """Show a run's state, its open gates and its last events, or list all runs."""
    with closing(open_store(db)) as store:
        if run_id is None:
            for run in store.list_runs():
                _out.print(
                    f"{run.id}  {run.status.value}  {run.stop_reason.value if run.stop_reason else '-'}"
                )
            return
        run = store.get_run(run_id)
        _out.print(
            f"{run.id}: {run.status.value}, stop_reason={run.stop_reason.value if run.stop_reason else '-'}"
        )
        for gate in store.pending_gates(run_id):
            _out.print(f"gate {gate.gate_id} ({gate.kind.value}): answer one of {gate.options}", markup=False)
        for event in store.events_after(run_id)[-8:]:
            _out.print(
                f"  #{event.seq} {event.kind.value} {event.node_id or ''} {event.payload or ''}", markup=False
            )
    source = run_dir(runs, run_id) / SOURCE_FILE
    if source.exists():
        _out.print(f"source: {source}", markup=False)


@runs_app.command("decide")
def decide(
    run_id: Annotated[str, typer.Argument(help="The run id.")],
    decision: Annotated[str, typer.Argument(help="One of the open gate's options, e.g. approve or reject.")],
    db: Annotated[Path, _DB] = _DEFAULT_DB,
) -> None:
    """Answer the run's one open gate; the worker continues the run."""
    with closing(open_store(db)) as store:
        gates = store.pending_gates(run_id)
        if len(gates) != 1:
            raise typer.BadParameter(f"run {run_id} has {len(gates)} open gates; expected exactly one")
        answer = GateDecision(gate_id=gates[0].gate_id, decision=decision, at=datetime.now(UTC))
        try:
            store.enqueue_command(RunCommand(run_id=run_id, kind=CommandKind.RESUME, decision=answer))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    _out.print(f"{gates[0].gate_id}: {decision}", markup=False)
