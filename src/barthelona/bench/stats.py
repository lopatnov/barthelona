"""Paired benchmark statistics (issue #101): compare arms by task, report intervals, state what is detectable.

At 20 tasks a pass rate has a 95% interval of about +-22 points, so a gate is only meaningful when the
paired interval excludes zero and the effect is above the smallest effect the bench can detect.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean, stdev

from barthelona.bench.runner import TaskResult

_Z = 1.96  # 95% two-sided
_MDE_FACTOR = 2.8  # (z_0.975 + z_0.8): 5% two-sided test with 80% power
_BOOTSTRAP_ROUNDS = 10_000
_MASK64 = (1 << 64) - 1


def _splitmix64(state: int) -> Iterator[int]:
    """Deterministic 64-bit stream for bootstrap resampling (not security; no `random` module needed)."""
    while True:
        state = (state + 0x9E3779B97F4A7C15) & _MASK64
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        yield z ^ (z >> 31)


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float


@dataclass(frozen=True)
class PairedComparison:
    """Arm B minus arm A, task by task: the mean difference in pass rate with a bootstrap interval."""

    difference: Interval
    tasks: int
    smallest_detectable_effect: float  # 80% power; a smaller gate needs more tasks first

    @property
    def excludes_zero(self) -> bool:
        return self.difference.low > 0 or self.difference.high < 0


def pass_rates(results: Iterable[TaskResult], arm: str) -> dict[str, float]:
    """Per task, the fraction of seeds in which *arm* passed."""
    outcomes: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        if result.arm == arm:
            outcomes[result.task_id].append(result.passed)
    return {task: fmean(map(float, passed)) for task, passed in outcomes.items()}


def wilson(successes: int, total: int) -> Interval:
    """Wilson 95% interval of a proportion; the unpaired view of a single arm."""
    if total == 0:
        return Interval(0.0, 0.0, 1.0)
    p = successes / total
    denominator = 1 + _Z**2 / total
    centre = (p + _Z**2 / (2 * total)) / denominator
    margin = _Z * math.sqrt(p * (1 - p) / total + _Z**2 / (4 * total**2)) / denominator
    return Interval(p, max(0.0, centre - margin), min(1.0, centre + margin))


def compare_paired(
    baseline: Mapping[str, float], candidate: Mapping[str, float], seed: int = 0
) -> PairedComparison:
    """Paired bootstrap over the tasks both arms ran. Raises `ValueError` when no task is shared."""
    shared = sorted(baseline.keys() & candidate.keys())
    if not shared:
        raise ValueError("the arms share no task; nothing to pair")
    deltas = [candidate[task] - baseline[task] for task in shared]
    stream = _splitmix64(seed)
    count = len(deltas)
    means = sorted(
        fmean(deltas[next(stream) % count] for _ in range(count)) for _ in range(_BOOTSTRAP_ROUNDS)
    )
    low, high = means[int(0.025 * _BOOTSTRAP_ROUNDS)], means[int(0.975 * _BOOTSTRAP_ROUNDS) - 1]
    spread = stdev(deltas) if len(deltas) > 1 else 0.0
    return PairedComparison(
        difference=Interval(fmean(deltas), low, high),
        tasks=len(shared),
        smallest_detectable_effect=_MDE_FACTOR * spread / math.sqrt(len(deltas)),
    )


def seed_noise(results: Sequence[TaskResult], arm: str) -> float:
    """Standard deviation of the arm's overall pass rate across seeds (run-to-run noise); 0 with one seed."""
    per_seed: dict[int, list[bool]] = defaultdict(list)
    for result in results:
        if result.arm == arm:
            per_seed[result.seed].append(result.passed)
    rates = [fmean(map(float, passed)) for passed in per_seed.values()]
    return stdev(rates) if len(rates) > 1 else 0.0
