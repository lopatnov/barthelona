"""Bench results on disk (JSONL, one `TaskResult` per line) and the comparison table (issue #101)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from pydantic import ValidationError

from barthelona.bench.runner import TaskResult
from barthelona.bench.stats import compare_paired, pass_rates, seed_noise, wilson
from barthelona.bench.task import BenchError
from barthelona.domain.enums import StopReason


def append_result(path: Path, result: TaskResult) -> None:
    """Add one line; the file is the run's record, so a crash loses at most the task in flight."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(result.model_dump_json() + "\n")


def read_results(path: Path) -> list[TaskResult]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BenchError(f"cannot read {path}: {exc}") from exc
    try:
        return [TaskResult.model_validate_json(line) for line in lines if line.strip()]
    except ValidationError as exc:
        raise BenchError(f"{path}: {exc}") from exc


def result_model(result: TaskResult) -> str:
    """Catalog key of the model that answered first; empty when no attempt got an answer."""
    return result.attempts[0].served_by if result.attempts else ""


def latest_per_run(results: Iterable[TaskResult]) -> list[TaskResult]:
    """One result per (model, arm, task, seed): a rerun replaces the earlier row, in file order."""
    latest = {(result_model(r), r.arm, r.task_id, r.seed): r for r in results}
    return list(latest.values())


def finished_runs(results: Iterable[TaskResult], model: str) -> frozenset[tuple[str, str, int]]:
    """(arm, task, seed) of *model*'s runs that need no rerun; a run with no model answer does."""
    return frozenset(
        (r.arm, r.task_id, r.seed)
        for r in results
        if result_model(r) == model and r.stop_reason != StopReason.NO_MODEL_AVAILABLE
    )


@dataclass(frozen=True)
class ArmSummary:
    arm: str
    tasks: int
    seeds: int
    runs: int
    pass_rate: float
    pass_low: float
    pass_high: float
    first_try: float
    attempts_to_green: float | None  # mean attempts of the green runs
    tok_per_s: float | None  # mean over attempts that reported it
    seed_noise: float
    served_by: tuple[str, ...]


def summarize(results: Sequence[TaskResult], arm: str) -> ArmSummary:
    runs = [r for r in results if r.arm == arm]
    if not runs:
        raise BenchError(f"no results for arm {arm!r}")
    green = [r for r in runs if r.passed]
    speeds = [a.tok_per_s for r in runs for a in r.attempts if a.tok_per_s is not None]
    interval = wilson(len(green), len(runs))
    return ArmSummary(
        arm=arm,
        tasks=len({r.task_id for r in runs}),
        seeds=len({r.seed for r in runs}),
        runs=len(runs),
        pass_rate=interval.estimate,
        pass_low=interval.low,
        pass_high=interval.high,
        first_try=fmean(float(r.first_try) for r in runs),
        attempts_to_green=fmean(len(r.attempts) for r in green) if green else None,
        tok_per_s=fmean(speeds) if speeds else None,
        seed_noise=seed_noise(results, arm),
        served_by=tuple(sorted({a.served_by for r in runs for a in r.attempts if a.served_by})),
    )


def _percent(value: float) -> str:
    return f"{100 * value:.0f}%"


def _optional(value: float | None, template: str) -> str:
    return "-" if value is None else template.format(value)


def format_report(
    results: Sequence[TaskResult], baseline: str | None = None, model: str | None = None
) -> list[str]:
    """The arm table of each model (only *model* when given), one run per (arm, task, seed).

    Several models in one file get a heading each; their runs are never pooled.
    """
    unique = latest_per_run(results)
    models = list(dict.fromkeys(result_model(r) for r in unique if model in (None, result_model(r))))
    if not models:
        raise BenchError("no results to report" if model is None else f"no results for model {model!r}")
    if len(models) == 1:
        return _arm_table([r for r in unique if result_model(r) == models[0]], baseline)
    lines: list[str] = []
    for name in models:
        lines.append(f"model: {name or '(no answer)'}")
        lines.extend(_arm_table([r for r in unique if result_model(r) == name], baseline))
        lines.append("")
    return lines[:-1]


def _arm_table(results: Sequence[TaskResult], baseline: str | None) -> list[str]:
    """One text row per arm, then each other arm against *baseline* (the first arm by default)."""
    arms = list(dict.fromkeys(r.arm for r in results))
    if not arms:
        raise BenchError("no results to report")
    base = baseline or arms[0]
    lines = ["arm            runs  pass@1 (95% CI)    first try  attempts  tok/s  seed noise  served by"]
    for arm in arms:
        s = summarize(results, arm)
        interval = f"{_percent(s.pass_rate)} ({_percent(s.pass_low)}-{_percent(s.pass_high)})"
        lines.append(
            f"{s.arm:<14} {s.runs:>4}  {interval:<17}  {_percent(s.first_try):>9}  "
            f"{_optional(s.attempts_to_green, '{:.1f}'):>8}  {_optional(s.tok_per_s, '{:.0f}'):>5}  "
            f"{_percent(s.seed_noise):>10}  {', '.join(s.served_by) or '-'}"
        )
    lines.extend(_paired_lines(results, [a for a in arms if a != base], base))
    return lines


def _paired_lines(results: Iterable[TaskResult], others: list[str], base: str) -> list[str]:
    results = list(results)
    lines: list[str] = []
    for arm in others:
        c = compare_paired(pass_rates(results, base), pass_rates(results, arm))
        d = c.difference
        verdict = "excludes zero" if c.excludes_zero else "includes zero"
        lines.append(
            f"{arm} vs {base}: {100 * d.estimate:+.1f} points (95% CI {100 * d.low:+.1f} to "
            f"{100 * d.high:+.1f}, {verdict}) over {c.tasks} tasks; "
            f"smallest detectable effect {100 * c.smallest_detectable_effect:.1f} points"
        )
    return lines
