"""``barthelona bench``: run the local-model bake-off and report it (docs/architecture.md §20)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from barthelona.bench import (
    Arm,
    BenchError,
    RunSettings,
    TaskResult,
    load_prompts,
    load_suite,
)
from barthelona.bench.endpoint import EndpointError, served_models
from barthelona.bench.report import append_result, finished_runs, format_report, read_results
from barthelona.bench.suite import run_suite
from barthelona.cli._toolchain import ToolchainMissingError, ensure_toolchain
from barthelona.llm import CatalogError, Gateway, OpenAIChatBackend, load_catalog
from barthelona.llm.catalog import Catalog, ChainEntry, ModelTarget

bench_app = typer.Typer(help="Benchmark models on the dev tasks (architecture §20).", no_args_is_help=True)
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)

_BENCH_PROFILE = "bench"
_DEFAULT_PROFILE = "local-only"  # the bake-off measures local models


def _arms(names: list[str], fix_iterations: int) -> list[Arm]:
    known = {
        "single": Arm("single", 0),
        "fix": Arm("fix", fix_iterations),
        "c-gcc": Arm("c-gcc", fix_iterations, language="c"),
    }
    unknown = [name for name in names if name not in known]
    if unknown:
        raise typer.BadParameter(f"unknown arm {unknown[0]!r}; choose {', '.join(known)}")
    return [known[name] for name in names]


def _catalog(path: Path, profile: str, model: str | None) -> tuple[Catalog, str]:
    """The catalog and the profile to run; *model* pins the worker role to one catalog entry."""
    catalog = load_catalog(path)
    if model is None:
        return catalog, profile
    if model not in catalog.models:
        raise typer.BadParameter(f"unknown model {model!r}; the catalog has {', '.join(catalog.models)}")
    pinned = {**catalog.profiles, _BENCH_PROFILE: {"worker": [ChainEntry(model=model)]}}
    return catalog.model_copy(update={"profiles": pinned}), _BENCH_PROFILE


def _provider_target(catalog: Catalog, provider_id: str) -> ModelTarget:
    """Any catalog model of the provider: listing an endpoint needs its URL, not a particular model."""
    key, model = next((k, m) for k, m in catalog.models.items() if m.provider == provider_id)
    return ModelTarget(key=key, provider_id=provider_id, provider=catalog.providers[provider_id], model=model)


def _preflight(targets: list[ModelTarget]) -> None:
    """Stop before any task runs when the first worker endpoint is down or does not serve its model."""
    head = targets[0]
    try:
        served = asyncio.run(served_models(head))
    except EndpointError as exc:
        _err.print(f"[bold red]bench run failed:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    if head.model.model not in served:
        listing = ", ".join(served) or "no models"
        _err.print(
            f"[bold red]bench run failed:[/bold red] {head.provider_id} serves {listing}, "
            f"not {head.model.model!r}; load it first or pick another with --model"
        )
        raise typer.Exit(2)


@bench_app.command("models")
def models(
    catalog_path: Annotated[Path, typer.Option("--catalog", help="Model catalog.")] = Path(
        "config/models.yaml"
    ),
) -> None:
    """List the models each local endpoint in the catalog serves right now."""
    try:
        catalog = load_catalog(catalog_path)
    except CatalogError as exc:
        _err.print(f"[bold red]bench models failed:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    local = [
        pid
        for pid, provider in catalog.providers.items()
        if provider.local and provider.enabled and any(m.provider == pid for m in catalog.models.values())
    ]
    for provider_id in local:
        target = _provider_target(catalog, provider_id)
        try:
            served = asyncio.run(served_models(target))
        except EndpointError as exc:
            _out.print(f"{provider_id}: down ({exc})", markup=False)
            continue
        _out.print(f"{provider_id}: {', '.join(served) or 'no models loaded'}", markup=False)
    if not local:
        _out.print("no enabled local provider in the catalog", markup=False)


@bench_app.command("run")
def run(
    suite: Annotated[str, typer.Option(help="Suite under bench/tasks/.")] = "dev",  # NOSONAR S107
    dialect: Annotated[str, typer.Option(help="Task dialect directory: nasm, gas-intel, gas-att.")] = "nasm",
    arm: Annotated[
        list[str] | None, typer.Option(help="single, fix and/or c-gcc; default single and fix.")
    ] = None,
    seeds: Annotated[int, typer.Option(min=1, help="Seeds per task; 3 or more to measure noise.")] = 3,
    fix_iterations: Annotated[int, typer.Option(min=1, help="Fix attempts of the fix arm.")] = 3,
    task: Annotated[list[str] | None, typer.Option(help="Only these task ids.")] = None,
    model: Annotated[
        str | None, typer.Option(help="Catalog model key; default is the profile's chain.")
    ] = None,
    catalog_path: Annotated[Path, typer.Option("--catalog", help="Model catalog.")] = Path(
        "config/models.yaml"
    ),
    bench_root: Annotated[Path, typer.Option(help="Directory with tasks/ and prompts/.")] = Path("bench"),
    output: Annotated[Path, typer.Option(help="JSONL file the results are appended to.")] = Path(
        "var/bench/results.jsonl"
    ),
    temperature: Annotated[float, typer.Option(help="Sampling temperature (local models only).")] = 0.2,
    max_tokens: Annotated[int, typer.Option(help="Reply cap per attempt.")] = 4096,
    transport: Annotated[str, typer.Option(help="auto, wsl or local.")] = "auto",
    rerun: Annotated[
        bool, typer.Option("--rerun", help="Run again what --output already holds for this model.")
    ] = False,
) -> None:
    """Run the arms over the suite for several seeds and append every task result to --output.

    A stopped run continues where it left off: runs --output already holds for the model are skipped.
    """
    from barthelona.bench.c_arm import CGccVerifier
    from barthelona.bench.verifier import LadderVerifier
    from barthelona.cli import _make_executor

    try:
        catalog, resolved = _catalog(catalog_path, _DEFAULT_PROFILE, model)
        tasks = [t for t in load_suite(bench_root, suite, dialect) if not task or t.id in task]
        prompts = load_prompts(bench_root)
    except (CatalogError, BenchError, OSError) as exc:
        _err.print(f"[bold red]bench run failed:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    if not tasks:
        raise typer.BadParameter("no task matches")
    arms = _arms(arm or ["single", "fix"], fix_iterations)
    targets = catalog.resolve("worker", resolved)
    _preflight(targets)
    done = (
        frozenset() if rerun or not output.exists() else finished_runs(read_results(output), targets[0].key)
    )
    if done:
        _out.print(
            f"Skipping {len(done)} runs of {targets[0].key} already in {output}; --rerun repeats them."
        )
    executor = _make_executor(transport, "bench run")
    gateway = Gateway(catalog, {"openai_chat": OpenAIChatBackend()}, profile=resolved)

    def record(result: TaskResult) -> None:
        append_result(output, result)
        _out.print(f"{result.task_id:<14} {result.arm:<7} seed {result.seed}: {result.stop_reason}")

    async def go() -> None:
        try:
            await ensure_toolchain(executor)
            await run_suite(
                tasks,
                arms,
                range(seeds),
                gateway,
                CGccVerifier(executor, LadderVerifier(executor)),
                prompts,
                output.parent / "work",
                RunSettings(temperature=temperature, max_tokens=max_tokens),
                record,
                done,
            )
        finally:
            await executor.aclose()

    try:
        asyncio.run(go())
    except ToolchainMissingError as exc:
        _err.print(f"[bold red]bench run failed:[/bold red] {exc}")
        raise typer.Exit(2) from exc
    _out.print(f"Results appended to {output}; run `barthelona bench report {output}`.")


@bench_app.command("report")
def report(
    results: Annotated[Path, typer.Argument(help="JSONL file written by `bench run`.")],
    baseline: Annotated[str | None, typer.Option(help="Arm the others are compared with.")] = None,
    model: Annotated[str | None, typer.Option(help="Only this catalog model key.")] = None,
) -> None:
    """Print pass@1, first try, attempts, tok/s, seed noise and the paired comparison, per model."""
    try:
        lines = format_report(read_results(results), baseline, model)
    except BenchError as exc:
        _err.print(f"[bold red]bench report failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    for line in lines:
        _out.print(line, markup=False)
