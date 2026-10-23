"""Run statistics: every chunked run and its chunks in SQLite, read back as last runs and per-model totals.

The hackathon asks for per-model and per-agent numbers; this keeps them next to the output instead of in a
terminal scrollback. Rows are plain facts from the run result (tokens as the provider measured them, latency,
who served each chunk and why earlier chain entries were skipped); nothing here influences a run.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from barthelona.llm.markovian import MarkovianResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, label TEXT NOT NULL, profile TEXT NOT NULL,
    status TEXT NOT NULL, stop_reason TEXT NOT NULL, chunks INTEGER NOT NULL, tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL, standard_cost INTEGER NOT NULL, markovian_cost INTEGER NOT NULL,
    recalled INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS run_chunks (
    run_id INTEGER NOT NULL REFERENCES runs(id), idx INTEGER NOT NULL, served_by TEXT NOT NULL,
    tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL, latency_ms INTEGER NOT NULL,
    marker TEXT NOT NULL, fallbacks TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class RunRow:
    id: int
    label: str
    status: str
    chunks: int
    tokens_in: int
    tokens_out: int
    elapsed_ms: int
    recalled: int


@dataclass(frozen=True)
class ModelRow:
    served_by: str
    chunks: int
    tokens_in: int
    tokens_out: int
    avg_latency_ms: int
    fell_through: int  # chunks that were served only after an earlier chain entry failed or was skipped


class RunLog:
    def __init__(self, path: Path | str, clock: Callable[[], float] = time.time) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)
        self._clock = clock

    def close(self) -> None:
        self._db.close()

    def record(self, result: MarkovianResult, *, label: str, profile: str, recalled: int = 0) -> int:
        """Store one finished run with its chunks; returns the run id."""
        cursor = self._db.execute(
            "INSERT INTO runs (at, label, profile, status, stop_reason, chunks, tokens_in, tokens_out,"
            " standard_cost, markovian_cost, recalled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self._clock(), label[:80], profile, result.status, result.stop_reason.value, len(result.chunks),
             result.tokens_in, result.tokens_out, result.standard_cost, result.markovian_cost, recalled),
        )  # fmt: skip
        run_id = int(cursor.lastrowid or 0)
        self._db.executemany(
            "INSERT INTO run_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (run_id, chunk.index, chunk.served_by, chunk.tokens_in, chunk.tokens_out, chunk.latency_ms,
                 chunk.marker, " | ".join(chunk.fallbacks))
                for chunk in result.chunks
            ],
        )  # fmt: skip
        self._db.commit()
        return run_id

    def last_runs(self, limit: int = 10) -> list[RunRow]:
        rows = self._db.execute(
            "SELECT r.id, r.label, r.status, r.chunks, r.tokens_in, r.tokens_out,"
            " COALESCE((SELECT SUM(latency_ms) FROM run_chunks WHERE run_id = r.id), 0), r.recalled"
            " FROM runs r ORDER BY r.id DESC LIMIT ?",
            (limit,),
        )
        return [RunRow(*row) for row in rows]

    def per_model(self) -> list[ModelRow]:
        rows = self._db.execute(
            "SELECT served_by, COUNT(*), SUM(tokens_in), SUM(tokens_out), CAST(AVG(latency_ms) AS INTEGER),"
            " SUM(fallbacks <> '') FROM run_chunks GROUP BY served_by ORDER BY COUNT(*) DESC"
        )
        return [ModelRow(*row) for row in rows]
