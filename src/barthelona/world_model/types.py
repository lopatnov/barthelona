"""World Model types and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class EntityState(str, Enum):
    EMERGING = "emerging"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProvenanceKind(str, Enum):
    MANUAL = "manual"
    RSS = "rss"
    API = "api"
    INGEST = "ingest"
    RESOLVER = "resolver"


@dataclass
class Provenance:
    kind: ProvenanceKind
    at: datetime
    by: Optional[str] = None
    run_id: Optional[str] = None
    url: Optional[str] = None


@dataclass
class StoredProvenance:
    kind: ProvenanceKind
    at: str  # ISO string
    by: Optional[str] = None
    run_id: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Entity:
    type: str
    id: str
    source: StoredProvenance
    created_at: str
    updated_at: str
    attrs: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    name: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    state: EntityState = EntityState.ACTIVE


@dataclass
class Context:
    type: str
    id: str
    source: StoredProvenance
    created_at: str
    updated_at: str
    attrs: dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None
    schema_version: int = 1


@dataclass
class Relationship:
    id: str
    from_: str
    type: str
    to: str
    source: StoredProvenance
    created_at: str
    context: Optional[str] = None
    attrs: Optional[dict[str, Any]] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    schema_version: int = 1


@dataclass
class Fact:
    id: str
    about: str
    predicate: str
    value: Any
    source: StoredProvenance
    asserted_at: str
    confidence: float = 0.5
    context: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass
class WorldEvent:
    id: str
    kind: str
    payload: Any
    at: str
    seq: int


@dataclass
class AuditEntry:
    seq: int
    action: str
    by: str
    detail: str
    event_id: Optional[str] = None
    run_id: Optional[str] = None
    at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MergeProposal:
    id: str
    left_id: str
    right_id: str
    left_name: str
    right_name: str
    similarity: float
    reason: str
    status: str = "pending"  # pending, approved, rejected
    proposed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


@dataclass
class IngestObservation:
    external_id: str
    title: str
    at: str  # ISO string
    source: Provenance
    type: Optional[str] = None
    text: Optional[str] = None
    entities: list[IngestEntity] = field(default_factory=list)


@dataclass
class IngestEntity:
    type: str
    name: str


@dataclass
class IngestReport:
    processed: int = 0
    clusters: int = 0
    changed: bool = False
    skipped_unchanged: int = 0


@dataclass
class WorldModelOptions:
    namespace: str
    storage: str = "memory"
    directory: Optional[str] = None
    conflict_policy: str = "most-recent-wins"
    source_priority: Optional[list[str]] = None
    resolver_auto_merge_at: float = 0.85
    resolver_review_band: tuple[float, float] = (0.82, 0.85)
    clock: Optional[Any] = None  # callable returning datetime


class ConflictPolicy(str, Enum):
    MOST_RECENT_WINS = "most-recent-wins"
    HIGHEST_CONFIDENCE_WINS = "highest-confidence-wins"
    SOURCE_PRIORITY = "source-priority"
    MANUAL = "manual"


class MergeDecision(str, Enum):
    AUTO_MERGE = "auto-merge"
    REVIEW = "review"
    NEW = "new"