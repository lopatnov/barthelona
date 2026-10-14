"""The local training dataset under `var/training/` (architecture §19, D-036).

Layout:
- `samples.jsonl`: one `TrainingSample` per line, appended by the single worker process;
- `texts/<aa>/<sha256>.txt`: content-addressed UTF-8 prompts and responses, shared between samples.

A text file is written before the index line that references it, so the index never points at a missing
text. Nothing here sends data anywhere.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from barthelona.domain.training import TrainingAttempt, TrainingSample, Verdict
from barthelona.training.redaction import Redactor
from barthelona.training.settings import TrainingDataSettings

INDEX_NAME = "samples.jsonl"
TEXTS_NAME = "texts"


class DatasetError(Exception):
    """The dataset on disk is malformed."""


class TrainingDataSink(Protocol):
    """Where the engine reports each code-producing attempt once the oracles have judged it."""

    def record(self, attempt: TrainingAttempt, *, prompt: str, response: str) -> TrainingSample | None: ...


class DisabledSink:
    """The sink while collection is off: it keeps nothing."""

    def record(self, attempt: TrainingAttempt, *, prompt: str, response: str) -> None:
        return None


def _text_path(root: Path, sha256: str) -> Path:
    return root / TEXTS_NAME / sha256[:2] / f"{sha256}.txt"


class DatasetWriter:
    """Appends samples to a dataset directory, redacting secrets from every text first."""

    def __init__(self, root: Path, redactor: Redactor) -> None:
        self._root = root
        self._redact = redactor

    def record(self, attempt: TrainingAttempt, *, prompt: str, response: str) -> TrainingSample:
        sample = TrainingSample(
            attempt=attempt,
            prompt_sha256=self._store_text(prompt),
            response_sha256=self._store_text(response),
        )
        self._root.mkdir(parents=True, exist_ok=True)
        with (self._root / INDEX_NAME).open("a", encoding="utf-8", newline="\n") as index:
            index.write(sample.model_dump_json() + "\n")
        return sample

    def _store_text(self, text: str) -> str:
        data = self._redact(text).encode("utf-8")
        sha256 = hashlib.sha256(data).hexdigest()
        path = _text_path(self._root, sha256)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".tmp")
            partial.write_bytes(data)  # bytes keep the text exactly as hashed: no newline translation
            partial.replace(path)
        return sha256


class DatasetReader:
    """Reads a dataset directory; a missing directory is an empty dataset."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def samples(self) -> Iterator[TrainingSample]:
        index = self._root / INDEX_NAME
        if not index.exists():
            return
        with index.open(encoding="utf-8", newline="\n") as lines:
            for number, line in enumerate(lines, start=1):
                try:
                    yield TrainingSample.model_validate_json(line)
                except ValidationError as error:
                    raise DatasetError(f"{index}:{number}: not a valid sample: {error}") from error

    def text(self, sha256: str) -> str:
        return _text_path(self._root, sha256).read_bytes().decode("utf-8")


def open_sink(settings: TrainingDataSettings, secrets: Iterable[str]) -> TrainingDataSink:
    """The sink a run uses: a writer when collection is enabled, otherwise one that keeps nothing."""
    if not settings.enabled:
        return DisabledSink()
    return DatasetWriter(settings.directory, Redactor.of(secrets))


def count_verdicts(samples: Iterable[TrainingSample]) -> Counter[Verdict]:
    return Counter(sample.attempt.verdict for sample in samples)
