"""Zetaris rows become H-MEM memories, so each run recalls only the facts its task needs.

``--facts-sql`` puts a fixed set of rows in front of chunk 0. Seeding turns the registered knowledge tables
into long-term memories instead: every fact keeps its Zetaris table as source and a high confidence, H-MEM
ranks them against the task and returns the top few, and a re-seed reinforces rather than duplicates (the
trust ledger records both). The first run of a task therefore starts warm, before it has learned anything.
"""

from __future__ import annotations

from barthelona.llm.hmem import HMem
from barthelona.llm.zetaris import ZetarisConfig, run_sql

SEEDS: tuple[tuple[str, str, str], ...] = (
    (
        "barthelona_files.linux_x64_syscalls",
        "Linux x86-64 syscall",
        "SELECT number, name, arg1, arg2, arg3, arg4, arg5, arg6, note"
        " FROM barthelona_files.linux_x64_syscalls",
    ),
    (
        "barthelona_files.abi_facts",
        "ABI fact",
        "SELECT topic, fact FROM barthelona_files.abi_facts",
    ),
)
CONFIDENCE = 0.9
_EMPTY = {"", "None", "null"}


def fact_text(label: str, cells: tuple[str, ...]) -> str:
    """One row as a sentence-like fact, without its empty cells."""
    return f"{label}: " + " | ".join(cell for cell in cells if cell not in _EMPTY)


def seed_hmem(config: ZetarisConfig, store: HMem, domain: str = "assembly") -> int:
    """Write every registered knowledge row into H-MEM; returns the facts newly written."""
    written = 0
    for source, label, sql in SEEDS:
        rows = run_sql(config, sql, 1000).rows
        written += store.ingest(
            [fact_text(label, row) for row in rows],
            source=f"zetaris:{source}",
            domain=domain,
            tags=("zetaris", "knowledge"),
            layer="long_term",
            confidence=CONFIDENCE,
        )
    return written
