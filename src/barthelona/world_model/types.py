"""Types of the World Model shared state (docs/adr/D-058): entities, provenance and stable IDs.

The World Model records a run's requirement, test and attempt entities so parallel or later drafts plan from
the same state. Every entity is keyed externally and gets a stable ID derived from that key, so re-ingesting
the same run gives an empty diff. IDs mirror the TypeScript reference (`engines/world-model/index.ts`
`externalId`), so the slow integration test can assert the two implementations agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The external-key system every Barthelona entity is keyed under.
SYSTEM = "barthelona"

# Entity kinds. A new kind is a reviewed edit (D-058), not a free-form string.
RUN = "run"
REQUIREMENT = "requirement"
TEST = "test"
ATTEMPT = "attempt"

# Where the worker writes the shared store; the CLI and the UI read the same file (D-058).
DEFAULT_STORE = Path("var/world-model/barthelona.json")

_MASK32 = 0xFFFFFFFF
_SIGN = 0x80000000


def _sync_hash(content: str) -> str:
    """The TypeScript `syncHash`: 32-bit djb2, then the absolute value as 8 hex digits.

    ``(hash << 5) - hash`` is ``31 * hash``; JavaScript bitwise arithmetic wraps at 32 bits, so the port masks
    every step. ``Math.abs`` of the signed value gives the final digits.
    """
    h = 0
    for char in content:
        h = (31 * h + ord(char)) & _MASK32
    signed = h if h < _SIGN else h - _MASK32 - 1
    return format(abs(signed), "08x")


def external_id(kind: str, system: str, key: str) -> str:
    """The stable ID of an entity keyed by (kind, system, key); identical to the TS ``externalId``."""
    return f"ext_{_sync_hash(f'{kind}:{system}:{key}')}"


def run_key(run_id: str) -> str:
    return run_id


def requirement_key(run_id: str, requirement_id: str) -> str:
    return f"{run_id}:requirement:{requirement_id}"


def case_key(run_id: str, test_id: str) -> str:
    return f"{run_id}:test:{test_id}"


def attempt_key(run_id: str, index: int) -> str:
    return f"{run_id}:attempt:{index}"


def utc_now() -> str:
    """The timestamp provenance carries when a caller does not supply one."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Provenance:
    """Who wrote an entity, so the trust ledger is queryable (D-058)."""

    kind: str = SYSTEM
    at: str = ""  # ISO-8601 UTC; filled by the store when empty
    by: str | None = None  # the model that produced the data, or None for deterministic writes
    route: str = ""  # the gateway role or "worker"/"oracle"
    run_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """The provenance for the JSON snapshot; the TS bridge ignores fields it does not read."""
        return {"kind": self.kind, "at": self.at, "by": self.by, "route": self.route, "run_id": self.run_id}


@dataclass(frozen=True)
class WorldEntity:
    """One record in the World Model: a stable key, its attrs and the provenance of the write."""

    kind: str
    key: str
    attrs: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=Provenance)

    @property
    def id(self) -> str:
        return external_id(self.kind, SYSTEM, self.key)

    @property
    def run_id(self) -> str | None:
        value = self.attrs.get("run_id")
        return str(value) if value is not None else None

    @property
    def slug(self) -> str | None:
        value = self.attrs.get("slug")
        return str(value) if value is not None else None
