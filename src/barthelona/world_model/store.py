"""Event store for World Model - append-only event log with materialized views."""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .types import (
    AuditEntry,
    Context,
    Entity,
    Fact,
    MergeProposal,
    Relationship,
    WorldEvent,
)


@dataclass
class State:
    """Materialized view of the world state."""

    entities: dict[str, Entity] = field(default_factory=dict)
    contexts: dict[str, Context] = field(default_factory=dict)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    facts: dict[str, Fact] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # alias_id -> primary_id
    merge_queue: list[MergeProposal] = field(default_factory=list)


class EventStore:
    """
    Append-only event store with materialized views.

    Single-writer discipline: all writes go through a FIFO queue per instance.
    """

    def __init__(self, namespace: str, storage: str = "memory", directory: str | None = None):
        self.namespace = namespace
        self.storage = storage
        self.directory = directory
        self.state = State()
        self.events: list[WorldEvent] = []
        self.audit: list[AuditEntry] = []
        self._seq = 0
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[WorldEvent], None]] = []
        self._file_path: Path | None = None

        if storage == "file" and directory:
            self._file_path = Path(directory) / f"{namespace}.jsonl"
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_file()

    def _load_from_file(self) -> None:
        """Load events from file and rebuild state."""
        if not self._file_path or not self._file_path.exists():
            return

        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(Exception):
                    event_data = json.loads(line)
                    event = WorldEvent(
                        id=event_data["id"],
                        kind=event_data["kind"],
                        payload=event_data["payload"],
                        at=event_data["at"],
                        seq=event_data["seq"],
                    )
                    self.events.append(event)
                    self._apply_event(event)
                    if event.seq > self._seq:
                        self._seq = event.seq

    def _persist_event(self, event: WorldEvent) -> None:
        """Persist a single event to file."""
        if not self._file_path:
            return

        event_data = {
            "id": event.id,
            "kind": event.kind,
            "payload": event.payload,
            "at": event.at,
            "seq": event.seq,
        }
        with self._file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, separators=(",", ":")) + "\n")

    def persist(self) -> None:
        """Force persistence (no-op for file storage, events are persisted immediately)."""
        pass

    def subscribe(self, fn: Callable[[WorldEvent], None]) -> Callable[[], None]:
        """Subscribe to new events."""
        with self._lock:
            self._subscribers.append(fn)

        def unsubscribe() -> None:
            with self._lock:
                if fn in self._subscribers:
                    self._subscribers.remove(fn)

        return unsubscribe

    def append(self, kind: str, payload: Any, at: str) -> WorldEvent:
        """Append an event to the log."""
        with self._lock:
            self._seq += 1
            event = WorldEvent(
                id=str(uuid4()),
                kind=kind,
                payload=payload,
                at=at,
                seq=self._seq,
            )
            self.events.append(event)
            self._apply_event(event)
            self._persist_event(event)

            # Notify subscribers
            for fn in self._subscribers:
                with contextlib.suppress(Exception):
                    fn(event)

            return event

    def _apply_event(self, event: WorldEvent) -> None:
        """Apply an event to the materialized state."""
        self._dispatch_event(self.state, event)

    def _dispatch_event(self, state: State, event: WorldEvent) -> None:
        """Dispatch an event to the appropriate handler based on its kind."""
        if event.kind == "upsertEntity":
            self._apply_upsert_entity(state, event)
        elif event.kind == "upsertContext":
            self._apply_upsert_context(state, event)
        elif event.kind == "relate":
            self._apply_relate(state, event)
        elif event.kind == "assertFact":
            self._apply_assert_fact(state, event)
        elif event.kind == "alias":
            self._apply_alias(state, event)

    def _apply_upsert_entity(self, state: State, event: WorldEvent) -> None:
        entity = event.payload
        if isinstance(entity, Entity):
            resolved_id = self._resolve_alias_in_state(state, entity.id)
            entity.id = resolved_id
            state.entities[resolved_id] = entity

    def _apply_upsert_context(self, state: State, event: WorldEvent) -> None:
        context = event.payload
        if isinstance(context, Context):
            state.contexts[context.id] = context

    def _apply_relate(self, state: State, event: WorldEvent) -> None:
        relationship = event.payload
        if isinstance(relationship, Relationship):
            state.relationships[relationship.id] = relationship

    def _apply_assert_fact(self, state: State, event: WorldEvent) -> None:
        fact = event.payload
        if isinstance(fact, Fact):
            state.facts[fact.id] = fact

    def _apply_alias(self, state: State, event: WorldEvent) -> None:
        alias_data = event.payload
        if isinstance(alias_data, dict):
            alias_id = alias_data.get("aliasId")
            primary_id = alias_data.get("primaryId")
            if alias_id and primary_id:
                state.aliases[alias_id] = primary_id

    def resolve_alias(self, entity_id: str) -> str:
        """Resolve an entity ID through the alias chain."""
        visited = set()
        current = entity_id
        while current in self.state.aliases and current not in visited:
            visited.add(current)
            current = self.state.aliases[current]
        return current

    def log_audit(
        self,
        action: str,
        by: str,
        detail: str,
        event_id: str | None = None,
        run_id: str | None = None,
        at: str | None = None,
    ) -> None:
        """Log an audit entry."""
        with self._lock:
            entry = AuditEntry(
                seq=len(self.audit) + 1,
                action=action,
                by=by,
                detail=detail,
                event_id=event_id,
                run_id=run_id,
                at=at or datetime.now().isoformat(),
            )
            self.audit.append(entry)

    def fold_until(self, at: str) -> State:
        """
        Fold events up to a given timestamp to produce a historical state.
        """
        temp_state = State()
        for event in self.events:
            if event.at > at:
                break
            # Apply event to temp state
            self._apply_event_to_state(temp_state, event)
        return temp_state

    def _apply_event_to_state(self, state: State, event: WorldEvent) -> None:
        """Apply an event to a given state object."""
        self._dispatch_event(state, event)

    def _resolve_alias_in_state(self, state: State, entity_id: str) -> str:
        """Resolve an entity ID through the alias chain in a given state."""
        visited = set()
        current = entity_id
        while current in state.aliases and current not in visited:
            visited.add(current)
            current = state.aliases[current]
        return current


def world_state_shape(store: EventStore) -> dict[str, Any]:
    """Generate a canonical representation of the world state for comparison."""
    return {
        "entities": {
            eid: {
                "type": e.type,
                "id": e.id,
                "attrs": e.attrs,
                "name": e.name,
                "aliases": e.aliases,
                "state": e.state.value,
            }
            for eid, e in sorted(store.state.entities.items())
        },
        "contexts": {
            cid: {
                "type": c.type,
                "id": c.id,
                "attrs": c.attrs,
                "parent": c.parent,
            }
            for cid, c in sorted(store.state.contexts.items())
        },
        "relationships": {
            rid: {
                "id": r.id,
                "from": r.from_,
                "type": r.type,
                "to": r.to,
                "context": r.context,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
            }
            for rid, r in sorted(store.state.relationships.items())
        },
        "facts": {
            fid: {
                "id": f.id,
                "about": f.about,
                "predicate": f.predicate,
                "value": f.value,
                "confidence": f.confidence,
                "context": f.context,
                "superseded_by": f.superseded_by,
            }
            for fid, f in sorted(store.state.facts.items())
        },
        "aliases": dict(sorted(store.state.aliases.items())),
    }
