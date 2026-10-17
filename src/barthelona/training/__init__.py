"""Opt-in collection of training data for an assembly-programming model (D-036). Local files only."""

from __future__ import annotations

from barthelona.training.dataset import (
    DatasetError,
    DatasetReader,
    DatasetWriter,
    DisabledSink,
    TrainingDataSink,
    count_verdicts,
    open_sink,
)
from barthelona.training.redaction import REDACTED, Redactor
from barthelona.training.settings import TrainingDataSettings

__all__ = [
    "REDACTED",
    "DatasetError",
    "DatasetReader",
    "DatasetWriter",
    "DisabledSink",
    "Redactor",
    "TrainingDataSettings",
    "TrainingDataSink",
    "count_verdicts",
    "open_sink",
]
