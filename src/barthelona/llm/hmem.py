"""H-MEM memory after the Meterless spec (Apache-2.0, github.com/Meterless/Meterless/tree/main/engines/hmem).

A small SQLite store of memories with provenance. ``query`` ranks them with the spec's hybrid score and
packages the winners as a ``[MEMORY CONTEXT]`` block for the first chunk of a Markovian run; ``ingest``
writes what a run learned back, with every mutation appended to a ledger table.

Differences from the spec, on purpose and by size: no embeddings, so the semantic signal (weight 0.35) is
absent and the other six weights are renormalised to sum to 1; no dreaming, sleep cycle, conflict
resolution or human approval gate. Retrieval defaults follow the spec (top 5) except the threshold, which is
lower (0.1, the value the spec's own Markovian example passes) because lexical-only scores run lower.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Layer = Literal["short_term", "working", "long_term"]

TOP_N = 5
THRESHOLD = 0.1
MAX_ENTITIES = 10  # spec cap per memory
_LAYER_WEIGHT: dict[str, float] = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
_WEIGHTS = {"keyword": 0.20, "tag": 0.10, "domain": 0.10, "entity": 0.15, "layer": 0.05, "recency": 0.05}
_SUPERSEDED_PENALTY = 0.20
_RECENCY_TAU_S = 14 * 86400.0  # spec: exponential decay, about 14 days
_QUERY_TOKENS = 8  # spec: Jaccard over the top-8 query tokens
_MIN_FACT_CHARS = 24
_MAX_FACT_CHARS = 400
_TOKEN = re.compile(r"[a-z0-9_.]{2,}")
_ENTITY = re.compile(r"`([^`\n]{2,40})`|\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b|\b([A-Z][A-Z0-9]{2,})\b")
_FACT_LABEL = re.compile(
    r"\b(DECISIONS|CONTEXT)\s*:\s*(.+?)(?=\s*\b(?:COMPLETED|REMAINING|DECISIONS|CONTEXT)\s*:|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, type TEXT NOT NULL,
    layer TEXT NOT NULL, domain TEXT NOT NULL, tags TEXT NOT NULL, entities TEXT NOT NULL,
    confidence REAL NOT NULL, source TEXT NOT NULL CHECK (source <> ''),
    created REAL NOT NULL, last_accessed REAL NOT NULL, access_count INTEGER NOT NULL DEFAULT 0,
    superseded_by INTEGER
);
CREATE TABLE IF NOT EXISTS ledger (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, op TEXT NOT NULL,
    memory_id INTEGER NOT NULL, source TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Memory:
    id: int
    content: str
    layer: str
    domain: str
    source: str
    confidence: float
    score: float = 0.0


@dataclass(frozen=True)
class Recall:
    """What a query found, and the block to put in front of the first chunk."""

    memories: tuple[Memory, ...]
    context: str


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _entities(text: str) -> list[str]:
    found = (next(group for group in match.groups() if group) for match in _ENTITY.finditer(text))
    return list(dict.fromkeys(name.lower() for name in found))[:MAX_ENTITIES]


def _overlap(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 0.0


def facts_from_state(state: str) -> list[str]:
    """The durable parts of a Markovian state block: its DECISIONS and CONTEXT lines."""
    facts = (" ".join(match.group(2).split())[:_MAX_FACT_CHARS] for match in _FACT_LABEL.finditer(state))
    return [fact for fact in facts if len(fact) >= _MIN_FACT_CHARS]


class HMem:
    def __init__(self, path: Path | str = ":memory:", clock: Callable[[], float] = time.time) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)
        self._clock = clock

    def close(self) -> None:
        self._db.close()

    def count(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0])

    def ledger_size(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0])

    def ingest(
        self,
        facts: Iterable[str],
        *,
        source: str,
        domain: str,
        tags: Iterable[str] = (),
        layer: Layer = "working",
        confidence: float = 0.8,
    ) -> int:
        """Store each new fact with provenance; a stored fact is reinforced. Returns the facts written."""
        if not source:
            raise ValueError("a memory without a source is rejected")
        now = self._clock()
        written = 0
        for fact in facts:
            row = self._db.execute("SELECT id FROM memories WHERE content = ?", (fact,)).fetchone()
            if row:
                self._db.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (now, row[0]),
                )
                self._log("reinforce", row[0], source)
                continue
            cursor = self._db.execute(
                "INSERT INTO memories (content, type, layer, domain, tags, entities, confidence, source,"
                " created, last_accessed) VALUES (?, 'factual', ?, ?, ?, ?, ?, ?, ?, ?)",
                (fact, layer, domain, json.dumps(sorted(tags)), json.dumps(_entities(fact)), confidence,
                 source, now, now),
            )  # fmt: skip
            self._log("write", int(cursor.lastrowid or 0), source)
            written += 1
        self._db.commit()
        return written

    def query(
        self,
        text: str,
        *,
        domain: str,
        tags: Iterable[str] = (),
        top_n: int = TOP_N,
        threshold: float = THRESHOLD,
    ) -> Recall:
        """The spec's hybrid ranking over the stored memories, packaged for chunk 0."""
        now = self._clock()
        counts = Counter(_tokens(text))
        top_query = {word for word, _ in counts.most_common(_QUERY_TOKENS)}
        query_entities, query_tags = set(_entities(text)), {tag.lower() for tag in tags}
        scored: list[Memory] = []
        for row in self._db.execute(
            "SELECT id, content, layer, domain, tags, entities, confidence, source, last_accessed,"
            " superseded_by FROM memories"
        ):
            id_, content, layer, mem_domain, mem_tags, mem_entities, confidence, source, accessed, newer = row
            signals = {
                "keyword": _overlap(top_query, set(_tokens(content))),
                "tag": _overlap(query_tags, {tag.lower() for tag in json.loads(mem_tags)}),
                "domain": 1.0 if mem_domain == domain else 0.0,
                "entity": len(query_entities & set(json.loads(mem_entities))) / len(query_entities)
                if query_entities
                else 0.0,
                "layer": _LAYER_WEIGHT[layer],
                "recency": math.exp(-max(0.0, now - accessed) / _RECENCY_TAU_S),
            }
            raw = sum(_WEIGHTS[name] * value for name, value in signals.items()) / sum(_WEIGHTS.values())
            raw -= _SUPERSEDED_PENALTY if newer is not None else 0.0
            score = min(1.0, max(0.0, raw)) * confidence
            if score >= threshold:
                scored.append(Memory(id_, content, layer, mem_domain, source, confidence, round(score, 4)))
        winners = tuple(sorted(scored, key=lambda memory: -memory.score)[:top_n])
        for memory in winners:
            self._db.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (now, memory.id),
            )
            self._log("recall", memory.id, "query")
        self._db.commit()
        return Recall(winners, _format(winners))

    def _log(self, op: str, memory_id: int, source: str) -> None:
        self._db.execute(
            "INSERT INTO ledger (at, op, memory_id, source) VALUES (?, ?, ?, ?)",
            (self._clock(), op, memory_id, source),
        )


def _format(memories: tuple[Memory, ...]) -> str:
    if not memories:
        return ""
    lines = [
        f"- {memory.content} (source: {memory.source}, relevance {memory.score:.2f})" for memory in memories
    ]
    return "[MEMORY CONTEXT]\nWhat earlier runs learned. Use it, do not re-decide it:\n" + "\n".join(lines)
