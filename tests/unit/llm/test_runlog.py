"""Run statistics: runs and chunks stored, last-runs table and per-model totals read back."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from barthelona.domain.enums import StopReason
from barthelona.llm.markovian import ChunkStat, MarkovianResult
from barthelona.llm.runlog import RunLog


def _chunk(
    index: int, served_by: str, tokens_out: int, latency_ms: int, fallbacks: tuple[str, ...] = ()
) -> ChunkStat:
    return ChunkStat(
        index=index,
        tokens_in=100,
        tokens_out=tokens_out,
        tokens=tokens_out,
        token_source="measured",
        latency_ms=latency_ms,
        served_by=served_by,
        marker="checkpoint",
        carryover="state_block",
        fallbacks=fallbacks,
    )


def _result(*chunks: ChunkStat) -> MarkovianResult:
    return MarkovianResult("text", StopReason.GREEN, chunks, carryover_tokens=128)


def test_last_runs_show_newest_first_with_totals_and_recall() -> None:
    log = RunLog(":memory:")
    log.record(
        _result(_chunk(0, "a", 50, 1000), _chunk(1, "a", 70, 2000)), label="first", profile="meterless"
    )
    log.record(_result(_chunk(0, "a", 40, 500)), label="second", profile="meterless", recalled=3)
    newest, oldest = log.last_runs()
    assert (newest.label, newest.chunks, newest.recalled, newest.elapsed_ms) == ("second", 1, 3, 500)
    assert (oldest.chunks, oldest.tokens_in, oldest.tokens_out, oldest.elapsed_ms) == (2, 200, 120, 3000)


def test_per_model_totals_count_tokens_latency_and_fall_throughs() -> None:
    log = RunLog(":memory:")
    log.record(
        _result(
            _chunk(0, "meterless_auto", 50, 1000),
            _chunk(1, "meterless_auto", 70, 3000),
            _chunk(2, "local_main", 20, 9000, fallbacks=("meterless_auto: boom",)),
        ),
        label="x",
        profile="meterless",
    )
    by_model = {row.served_by: row for row in log.per_model()}
    assert by_model["meterless_auto"].chunks == 2
    assert by_model["meterless_auto"].avg_latency_ms == 2000
    assert by_model["meterless_auto"].fell_through == 0
    assert (by_model["local_main"].tokens_out, by_model["local_main"].fell_through) == (20, 1)


def test_per_model_totals_separate_the_models_that_answered_behind_one_catalog_key() -> None:
    log = RunLog(":memory:")
    first = ChunkStat(**{**_chunk(0, "meterless_auto", 10, 100).__dict__, "answered_by": "nvidia/nemotron"})
    second = ChunkStat(**{**_chunk(1, "meterless_auto", 20, 300).__dict__, "answered_by": "poolside/laguna"})
    log.record(_result(first, second), label="x", profile="p")
    rows = {row.answered_by: row for row in log.per_model()}
    assert set(rows) == {"nvidia/nemotron", "poolside/laguna"}
    assert rows["poolside/laguna"].avg_latency_ms == 300


def test_a_database_from_before_the_answered_by_column_is_migrated(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite"
    with sqlite3.connect(db) as old:
        old.executescript(
            "CREATE TABLE run_chunks (run_id INTEGER NOT NULL, idx INTEGER NOT NULL, served_by TEXT NOT NULL,"
            " tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL, latency_ms INTEGER NOT NULL,"
            " marker TEXT NOT NULL, fallbacks TEXT NOT NULL);"
        )
    log = RunLog(db)
    assert log.per_model() == []
    log.close()


def test_limit_caps_the_last_runs_table() -> None:
    log = RunLog(":memory:")
    for index in range(5):
        log.record(_result(_chunk(0, "a", 1, 1)), label=str(index), profile="p")
    assert [row.label for row in log.last_runs(limit=2)] == ["4", "3"]
