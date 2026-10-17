"""Benchmark harness: tasks, arms, the fix-loop runner and paired statistics (docs/architecture.md §20)."""

from barthelona.bench.prompts import PromptSet, load_prompts, render_feedback
from barthelona.bench.runner import Arm, AttemptResult, RunSettings, TaskResult, TaskRun, Verifier, run_task
from barthelona.bench.stats import Interval, PairedComparison, compare_paired, pass_rates, seed_noise, wilson
from barthelona.bench.task import BenchError, BenchTask, load_suite, load_task

__all__ = [
    "Arm",
    "AttemptResult",
    "BenchError",
    "BenchTask",
    "Interval",
    "PairedComparison",
    "PromptSet",
    "RunSettings",
    "TaskResult",
    "TaskRun",
    "Verifier",
    "compare_paired",
    "load_prompts",
    "load_suite",
    "load_task",
    "pass_rates",
    "render_feedback",
    "run_task",
    "seed_noise",
    "wilson",
]
