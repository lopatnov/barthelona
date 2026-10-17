"""Run a suite: every task under every arm and seed, one at a time (the resident model is the bottleneck)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from barthelona.bench.prompts import PromptSet
from barthelona.bench.runner import Arm, RunSettings, TaskResult, TaskRun, Verifier, run_task
from barthelona.bench.task import BenchTask
from barthelona.llm import ModelGateway


async def run_suite(
    tasks: Sequence[BenchTask],
    arms: Sequence[Arm],
    seeds: Sequence[int],
    gateway: ModelGateway,
    verifier: Verifier,
    prompts: PromptSet,
    work_root: Path,
    settings: RunSettings,
    on_result: Callable[[TaskResult], None],
) -> list[TaskResult]:
    """Seed by seed, so an interrupted run holds complete seeds; `on_result` sees each result at once."""
    results: list[TaskResult] = []
    for seed in seeds:
        for task in tasks:
            run = TaskRun(task, seed, gateway, verifier, prompts, task.source_name, work_root, settings)
            for arm in arms:
                result = await run_task(run, arm)
                on_result(result)
                results.append(result)
    return results
