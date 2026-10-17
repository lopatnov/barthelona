"""Paired comparison, Wilson intervals and seed noise."""

from __future__ import annotations

import pytest

from barthelona.bench import TaskResult, compare_paired, pass_rates, seed_noise, wilson
from barthelona.domain.enums import StopReason


def _result(task: str, arm: str, seed: int, passed: bool) -> TaskResult:
    stop = StopReason.GREEN if passed else StopReason.MAX_ATTEMPTS
    return TaskResult(task_id=task, arm=arm, seed=seed, stop_reason=stop, attempts=())


def test_wilson_matches_the_textbook_value() -> None:
    interval = wilson(10, 20)
    assert interval.estimate == 0.5
    assert interval.low == pytest.approx(0.299, abs=0.002)
    assert interval.high == pytest.approx(0.701, abs=0.002)


def test_wilson_of_nothing_is_the_whole_range() -> None:
    interval = wilson(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_pass_rates_average_over_seeds_per_task() -> None:
    results = [
        _result("a", "x", 0, True),
        _result("a", "x", 1, False),
        _result("b", "x", 0, True),
        _result("a", "y", 0, True),
    ]
    assert pass_rates(results, "x") == {"a": 0.5, "b": 1.0}


def test_a_consistent_gain_excludes_zero() -> None:
    baseline = {f"t{i}": 0.0 for i in range(12)}
    candidate = {f"t{i}": 1.0 for i in range(12)}
    comparison = compare_paired(baseline, candidate)
    assert comparison.difference.estimate == 1.0
    assert comparison.excludes_zero
    assert comparison.smallest_detectable_effect == 0.0


def test_a_noisy_small_gain_does_not_exclude_zero() -> None:
    baseline = {f"t{i}": 0.0 for i in range(10)}
    candidate = {f"t{i}": 1.0 if i < 2 else 0.0 for i in range(10)}
    comparison = compare_paired(baseline, candidate)
    assert comparison.difference.estimate == pytest.approx(0.2)
    assert comparison.smallest_detectable_effect > 0.2
    assert comparison.difference.low == 0.0
    assert not comparison.excludes_zero


def test_only_shared_tasks_are_paired_and_no_overlap_is_an_error() -> None:
    assert compare_paired({"a": 0.0, "b": 1.0}, {"a": 1.0, "c": 0.0}).tasks == 1
    with pytest.raises(ValueError, match="share no task"):
        compare_paired({"a": 0.0}, {"b": 1.0})


def test_the_bootstrap_is_reproducible() -> None:
    baseline = {f"t{i}": float(i % 2) for i in range(8)}
    candidate = {f"t{i}": float((i + 1) % 3 == 0) for i in range(8)}
    first = compare_paired(baseline, candidate, seed=1)
    second = compare_paired(baseline, candidate, seed=1)
    assert (first.difference, first.tasks) == (second.difference, second.tasks)


def test_seed_noise_is_the_spread_of_per_seed_pass_rates() -> None:
    results = [_result(f"t{i}", "x", seed, i < 2 + seed) for seed in range(3) for i in range(4)]
    assert seed_noise(results, "x") == pytest.approx(0.25)
    assert seed_noise(results[:4], "x") == 0.0
