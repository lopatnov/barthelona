"""Training-data samples (docs/architecture.md §19 "Training data", D-036).

A sample describes one code-producing model attempt and what the oracles said about it. The prompt and
the response are stored as separate text files and referenced here by sha256, so code never travels
inside this JSON (invariant 5).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain._base import Document, DomainModel, ItemId, NodeId, Sha256
from barthelona.domain.enums import Role, StoryKind
from barthelona.domain.project import TargetProfile
from barthelona.domain.run import ProviderId
from barthelona.domain.verification import LevelResult


class SampleSource(StrEnum):
    """Where an attempt came from. The holdout benchmark has no member: it never becomes training data."""

    RUN = "run"
    BENCH_DEV = "bench_dev"


class Verdict(StrEnum):
    """The oracles' judgement of an attempt; an LLM never sets it."""

    ACCEPTED = "accepted"  # at least one level passed and none failed
    REJECTED = "rejected"  # at least one level failed
    NOT_VERIFIED = "not_verified"  # no level passed or failed, e.g. the envelope did not parse


class TrainingAttempt(DomainModel):
    """What is known about one attempt apart from its texts."""

    run_id: ItemId
    seq: int = Field(ge=0)  # the attempt's LLM-call number within the run
    recorded_at: datetime
    source: SampleSource  # required, so a caller always decides; the engine refuses holdout runs
    target: TargetProfile
    story_kind: StoryKind | None = None
    task_id: NodeId | None = None
    node_id: NodeId
    role: Role
    attempt: int = Field(ge=1)  # 1 for the first try at this task node
    provider: ProviderId
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    model_hash: Sha256 | None = None
    local: bool  # served by a local provider; cloud outputs may carry provider terms (D-036)
    levels: list[LevelResult] = Field(default_factory=list)
    improves_on_seq: int | None = Field(default=None, ge=0)  # the failed attempt this one retries

    @model_validator(mode="after")
    def _is_a_model_attempt(self) -> TrainingAttempt:
        if self.role is Role.DET:
            raise ValueError("deterministic nodes make no model calls, so they produce no samples")
        if self.improves_on_seq is not None and self.improves_on_seq >= self.seq:
            raise ValueError(f"improves_on_seq {self.improves_on_seq} must precede seq {self.seq}")
        return self

    @property
    def verdict(self) -> Verdict:
        statuses = {result.status for result in self.levels}
        if "fail" in statuses:
            return Verdict.REJECTED
        # Skipped or unsupported levels confirm nothing; a gate that did not pass does not pass (invariant 1).
        if "pass" in statuses:
            return Verdict.ACCEPTED
        return Verdict.NOT_VERIFIED


class TrainingSample(Document):
    """One line of the dataset index (`var/training/samples.jsonl`)."""

    attempt: TrainingAttempt
    prompt_sha256: Sha256  # texts/<sha256>.txt, after redaction
    response_sha256: Sha256

    @property
    def sample_id(self) -> str:
        return f"{self.attempt.run_id}.{self.attempt.seq}"
