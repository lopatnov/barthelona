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
from barthelona.bench.report import append_result, format_report, read_results
from barthelona.bench.suite import run_suite
from barthelona.llm import CatalogError, Gateway, OpenAIChatBackend, load_catalog
from barthelona.llm.catalog import Catalog, ChainEntry

bench_app = typer.Typer(help="Benchmark models on the dev tasks (architecture §20).", no_args_is_help=True)
_out = Console(soft_wrap=True, highlight=False)
_err = Console(stderr=True, soft_wrap=True, highlight=False)

_BENCH_PROFILE = "bench"
_DEFAULT_PROFILE = "local-only"  # the bake-off measures local models


def _arms(names: list[str], fix_iterations: int) -> list[Arm]:
    known = {"single": Arm("single", 0), "fix": Arm("fix", fix_iterations)}
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


@bench_app.command("run")
def run(
    suite: Annotated[str, typer.Option(help="Suite under bench/tasks/.")] = "dev",
    dialect: Annotated[str, typer.Option(help="Task dialect directory: nasm, gas-intel, gas-att.")] = "nasm",
    arm: Annotated[list[str] | None, typer.Option(help="single and/or fix; default both.")] = None,
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
) -> None:
    """Run the arms over the suite for several seeds and append every task result to --output."""
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
    executor = _make_executor(transport, "bench run")
    gateway = Gateway(catalog, {"openai_chat": OpenAIChatBackend()}, profile=resolved)

    def record(result: TaskResult) -> None:
        append_result(output, result)
        _out.print(f"{result.task_id:<14} {result.arm:<7} seed {result.seed}: {result.stop_reason}")

    async def go() -> None:
        try:
            await run_suite(
                tasks,
                arms,
                range(seeds),
                gateway,
                LadderVerifier(executor),
                prompts,
                output.parent / "work",
                RunSettings(temperature=temperature, max_tokens=max_tokens),
                record,
            )
        finally:
            await executor.aclose()

    asyncio.run(go())
    _out.print(f"Results appended to {output}; run `barthelona bench report {output}`.")


@bench_app.command("report")
def report(
    results: Annotated[Path, typer.Argument(help="JSONL file written by `bench run`.")],
    baseline: Annotated[str | None, typer.Option(help="Arm the others are compared with.")] = None,
) -> None:
    """Print pass@1, first try, attempts, tok/s, seed noise and the paired comparison."""
    try:
        lines = format_report(read_results(results), baseline)
    except BenchError as exc:
        _err.print(f"[bold red]bench report failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    for line in lines:
        _out.print(line, markup=False)
