"""Training-sample models (D-036): the verdict comes from oracle results, and the bounds hold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from barthelona.domain import (
    DOCUMENTS,
    Level,
    LevelResult,
    Role,
    Run,
    SampleSource,
    TargetProfile,
    TrainingAttempt,
    TrainingSample,
    Verdict,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _attempt(target: TargetProfile, **changes: Any) -> TrainingAttempt:
    fields: dict[str, Any] = {
        "run_id": "r1",
        "source": SampleSource.RUN,
        "seq": 3,
        "recorded_at": datetime(2026, 10, 14, tzinfo=UTC),
        "target": target,
        "node_id": "code",
        "role": Role.WORKER,
        "attempt": 1,
        "provider": "lmstudio",
        "model": "qwen3-coder-30b-a3b",
        "local": True,
    }
    return TrainingAttempt.model_validate(fields | changes)


def _level(level: Level, status: Literal["pass", "fail", "skipped"]) -> LevelResult:
    return LevelResult(level=level, status=status, secs=0.1)


def test_an_attempt_without_oracle_results_is_not_verified(target: TargetProfile) -> None:
    assert _attempt(target).verdict is Verdict.NOT_VERIFIED


def test_an_attempt_is_accepted_when_no_level_failed(target: TargetProfile) -> None:
    levels = [_level(Level.V0, "pass"), _level(Level.V1, "pass"), _level(Level.V3, "skipped")]
    assert _attempt(target, levels=levels).verdict is Verdict.ACCEPTED


@pytest.mark.parametrize("status", ["skipped", "unsupported"])
def test_levels_that_confirm_nothing_do_not_accept(target: TargetProfile, status: str) -> None:
    levels = [
        LevelResult(level="tamper", status=status, secs=0.0),
        LevelResult(level=Level.V0, status=status, secs=0.0),
    ]
    assert _attempt(target, levels=levels).verdict is Verdict.NOT_VERIFIED


def test_one_failed_level_rejects_the_attempt(target: TargetProfile) -> None:
    levels = [_level(Level.V0, "pass"), _level(Level.V2, "fail")]
    assert _attempt(target, levels=levels).verdict is Verdict.REJECTED


def test_deterministic_nodes_produce_no_samples(target: TargetProfile) -> None:
    with pytest.raises(ValidationError, match="deterministic nodes"):
        _attempt(target, role=Role.DET)


@pytest.mark.parametrize("improves_on_seq", [3, 4])
def test_a_retry_improves_on_an_earlier_attempt_only(target: TargetProfile, improves_on_seq: int) -> None:
    with pytest.raises(ValidationError, match="must precede"):
        _attempt(target, improves_on_seq=improves_on_seq)


def test_holdout_is_not_a_sample_source(target: TargetProfile) -> None:
    with pytest.raises(ValidationError):
        _attempt(target, source="bench_holdout")


def test_sample_references_texts_by_hash_and_names_itself(target: TargetProfile) -> None:
    sample = TrainingSample(attempt=_attempt(target), prompt_sha256=SHA_A, response_sha256=SHA_B)
    assert sample.sample_id == "r1.3"
    assert TrainingSample.model_validate_json(sample.model_dump_json()) == sample
    with pytest.raises(ValidationError):
        TrainingSample(attempt=_attempt(target), prompt_sha256="not-a-hash", response_sha256=SHA_B)


def test_training_sample_is_a_listed_document() -> None:
    assert DOCUMENTS["TrainingSample"] is TrainingSample


def test_runs_do_not_collect_training_data_by_default(run: Run) -> None:
    assert run.collect_training_data is False
