"""World Model main class - event-sourced, deterministic, single-writer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .ingest import IngestObservation, IngestProcessor, IngestReport, world_state_shape
from .resolve import decide, jaccard, levenshtein, name_similarity

# Re-export for conformance suite
from .stable_ids import (
    canonical_json,
    context_id_from_attrs,
    entity_id_from_name,
    external_id,
    fact_id,
    normalize_name,
    relationship_id,
    sha256_hex,
)
from .store import EventStore
from .store import world_state_shape as store_world_state_shape
from .types import (
    AuditEntry,
    ConflictPolicy,
    Context,
    Entity,
    EntityState,
    Fact,
    IngestEntity,
    MergeDecision,
    MergeProposal,
    Provenance,
    ProvenanceKind,
    Relationship,
    StoredProvenance,
    WorldEvent,
    WorldModelOptions,
)


class WorldModel:
    """
    World Model - an event-sourced, deterministic shared state for agents.

    Single-writer discipline: every write goes through a FIFO queue per instance,
    so concurrent ingests serialize automatically.
    """

    def __init__(self, opts: WorldModelOptions):
        if not opts.namespace:
            raise ValueError("WorldModel: namespace is required")

        self.opts = opts
        self.clock = opts.clock or (lambda: datetime.now())
        self.store = EventStore(opts.namespace, opts.storage, opts.directory)
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._ingest_processor = IngestProcessor(self.store, lambda: int(self.clock().timestamp()))

    # ---------------------------------------------------------------- writes

    async def _enqueue(self, fn: Callable[[], Any]) -> Any:
        """Execute a write operation with single-writer serialization."""
        async with self._write_lock:
            return fn()

    def _normalize_provenance(self, source: Provenance | None) -> StoredProvenance:
        """Normalize provenance to stored format."""
        if not source or not source.kind or source.at is None:
            raise ValueError(
                "World Model: every write carries provenance (kind + at). "
                "No provenance, no write."
            )

        at = source.at.isoformat() if isinstance(source.at, datetime) else source.at
        return StoredProvenance(
            kind=source.kind,
            at=at,
            by=source.by,
            run_id=source.run_id,
            url=source.url,
        )

    async def upsert_entity(
        self,
        type: str,
        external_key: dict[str, str] | None = None,
        name: str | None = None,
        attrs: dict[str, Any] | None = None,
        source: Provenance | None = None,
        state: EntityState = EntityState.ACTIVE,
    ) -> Entity:
        """Upsert an entity."""
        return await self._enqueue(
            lambda: self._upsert_entity_sync(type, external_key, name, attrs, source, state)
        )

    def _upsert_entity_sync(
        self,
        type: str,
        external_key: dict[str, str] | None = None,
        name: str | None = None,
        attrs: dict[str, Any] | None = None,
        source: Provenance | None = None,
        state: EntityState = EntityState.ACTIVE,
    ) -> Entity:
        source_stored = self._normalize_provenance(source)

        if external_key:
            entity_id = external_id(type, external_key["system"], external_key["id"])
        else:
            if not name:
                raise ValueError("World Model: name-keyed entities need a name (or provide an externalKey)")
            entity_id = entity_id_from_name(type, name)

        # Resolution pass for name-keyed entities
        if not external_key and name:
            for other in self.store.state.entities.values():
                if other.type != type or other.id == entity_id or not other.name:
                    continue
                similarity = name_similarity(name, other.name)
                decision = decide(
                    similarity,
                    self.opts.resolver_auto_merge_at,
                    self.opts.resolver_review_band,
                )
                if decision == "auto-merge":
                    self.store.append("alias", {
                        "aliasId": entity_id,
                        "primaryId": other.id,
                        "mergedAt": source_stored.at,
                        "mergedBy": "resolver",
                        "reason": f"similarity {similarity:.3f}",
                    }, source_stored.at)
                    self.store.log_audit("auto-merge", "resolver",
                                        f"{name} -> {other.name} ({similarity:.3f})",
                                        None, None, source_stored.at)
                    return self._fold_entity_upsert(other.id, {
                        "type": type,
                        "attrs": attrs or {},
                    }, source_stored, name)
                elif decision == "review":
                    proposal_id = f"merge_{len(self.store.state.merge_queue) + 1}"
                    if not any(
                        (p.left_id == entity_id and p.right_id == other.id) or
                        (p.left_id == other.id and p.right_id == entity_id)
                        for p in self.store.state.merge_queue
                    ):
                        proposal = MergeProposal(
                            id=proposal_id,
                            left_id=entity_id,
                            right_id=other.id,
                            left_name=name,
                            right_name=other.name,
                            similarity=similarity,
                            reason="name similarity in review band [0.82, 0.85)",
                            status="pending",
                            proposed_at=source_stored.at,
                        )
                        self.store.state.merge_queue.append(proposal)
                        self.store.log_audit("merge-proposed", "resolver",
                                            f"{name} ~ {other.name} ({similarity:.3f}) queued",
                                            None, None, source_stored.at)

        result = self._fold_entity_upsert(entity_id, {
            "type": type,
            "attrs": attrs or {},
        }, source_stored, name)

        # Create external key alias for hash-based ID
        if external_key:
            self._create_external_key_alias(type, external_key, entity_id, source_stored)

        return result

    def _create_external_key_alias(
        self, type: str, external_key: dict[str, str], entity_id: str, source: StoredProvenance
    ) -> None:
        """Create an alias from external key format (type:system:id) to the hash-based entity ID."""
        external_key_str = f"{type}:{external_key['system']}:{external_key['id']}"
        if external_key_str not in self.store.state.aliases:
            self.store.append("alias", {
                "aliasId": external_key_str,
                "primaryId": entity_id,
                "mergedAt": source.at,
                "mergedBy": "system",
                "reason": "external key alias",
            }, source.at)
            self.store.log_audit(
                "alias", "system", f"{external_key_str} -> {entity_id}", None, None, source.at
            )

    def _fold_entity_upsert(
        self,
        entity_id: str,
        input_data: dict[str, Any],
        source: StoredProvenance,
        name: str | None,
    ) -> Entity:
        """Internal entity upsert that appends event. Updates existing entity if present."""
        resolved = self.store.resolve_alias(entity_id)

        # Check if entity already exists
        existing = self.store.state.entities.get(resolved)
        if existing:
            # Update existing entity - merge attrs, update timestamp
            new_attrs = {**existing.attrs, **(input_data.get("attrs") or {})}
            new_aliases = list(existing.aliases)
            if name and name not in new_aliases:
                new_aliases.append(name)

            existing.attrs = new_attrs
            existing.aliases = new_aliases
            existing.updated_at = source.at
            existing.source = source
            if input_data.get("state"):
                existing.state = input_data["state"]

            # Append event for the updated entity
            event = self.store.append("upsertEntity", existing, source.at)
            self.store.log_audit("upsertEntity", source.by or "system",
                               f"{resolved} ({input_data['type']})",
                               event.id, source.run_id, source.at)
            return existing
        else:
            # Create new entity
            entity = Entity(
                type=input_data["type"],
                id=resolved,
                attrs={**(input_data.get("attrs") or {})},
                schema_version=1,
                source=source,
                created_at=source.at,
                updated_at=source.at,
                name=name,
                aliases=[name] if name else [],
                state=input_data.get("state", EntityState.ACTIVE),
            )
            event = self.store.append("upsertEntity", entity, source.at)
            self.store.log_audit("upsertEntity", source.by or "system",
                               f"{resolved} ({input_data['type']})",
                               event.id, source.run_id, source.at)
            return self.store.state.entities[resolved]

    async def upsert_context(
        self,
        type: str,
        external_key: dict[str, str] | None = None,
        attrs: dict[str, Any] | None = None,
        parent: str | None = None,
        source: Provenance | None = None,
    ) -> Context:
        """Upsert a context."""
        return await self._enqueue(
            lambda: self._upsert_context_sync(type, external_key, attrs, parent, source)
        )

    def _upsert_context_sync(
        self,
        type: str,
        external_key: dict[str, str] | None = None,
        attrs: dict[str, Any] | None = None,
        parent: str | None = None,
        source: Provenance | None = None,
    ) -> Context:
        source_stored = self._normalize_provenance(source)

        if external_key:
            context_id = external_id(type, external_key["system"], external_key["id"])
        else:
            context_id = context_id_from_attrs(type, attrs or {}, parent)

        context = Context(
            type=type,
            id=context_id,
            attrs=attrs or {},
            parent=parent,
            schema_version=1,
            source=source_stored,
            created_at=source_stored.at,
            updated_at=source_stored.at,
        )
        event = self.store.append("upsertContext", context, source_stored.at)
        self.store.log_audit("upsertContext", source_stored.by or "system",
                           f"{context_id} ({type})", event.id, source_stored.run_id, source_stored.at)
        return self.store.state.contexts[context_id]

    async def relate(
        self,
        from_: str,
        type: str,
        to: str,
        context: str | None = None,
        attrs: dict[str, Any] | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        source: Provenance | None = None,
    ) -> Relationship:
        """Create a relationship."""
        return await self._enqueue(
            lambda: self._relate_sync(from_, type, to, context, attrs, valid_from, valid_to, source)
        )

    def _relate_sync(
        self,
        from_: str,
        type: str,
        to: str,
        context: str | None = None,
        attrs: dict[str, Any] | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        source: Provenance | None = None,
    ) -> Relationship:
        source_stored = self._normalize_provenance(source)
        from_resolved = self.store.resolve_alias(from_)
        to_resolved = self.store.resolve_alias(to)

        # For bitemporal edges: find and close any existing open edge with same from and type
        # A superseding edge is defined by same from_ and type; the to entity can change
        for existing_rel in self.store.state.relationships.values():
            if (existing_rel.from_ == from_resolved and
                existing_rel.type == type and
                existing_rel.valid_to is None):
                # Close the existing edge
                existing_rel.valid_to = valid_from or source_stored.at
                self.store.append("relate", existing_rel, source_stored.at)
                self.store.log_audit("relate", source_stored.by or "system",
                                   f"{from_resolved} -[{type}]-> {existing_rel.to} (closed)",
                                   None, source_stored.run_id, source_stored.at)
                break

        rel_id = relationship_id(from_resolved, type, to_resolved, context, valid_from, attrs)
        if rel_id in self.store.state.relationships:
            return self.store.state.relationships[rel_id]  # content-addressed no-op

        rel = Relationship(
            id=rel_id,
            from_=from_resolved,
            type=type,
            to=to_resolved,
            context=context,
            attrs=attrs,
            valid_from=valid_from or source_stored.at,
            valid_to=valid_to,
            schema_version=1,
            source=source_stored,
            created_at=source_stored.at,
        )
        event = self.store.append("relate", rel, source_stored.at)
        self.store.log_audit("relate", source_stored.by or "system",
                           f"{from_resolved} -[{type}]-> {to_resolved}",
                           event.id, source_stored.run_id, source_stored.at)
        return self.store.state.relationships[rel_id]

    async def assert_fact(
        self,
        about: str,
        predicate: str,
        value: Any,
        confidence: float = 0.5,
        context: str | None = None,
        source: Provenance | None = None,
    ) -> Fact:
        """Assert a fact."""
        return await self._enqueue(
            lambda: self._assert_fact_sync(about, predicate, value, confidence, context, source)
        )

    def _assert_fact_sync(
        self,
        about: str,
        predicate: str,
        value: Any,
        confidence: float = 0.5,
        context: str | None = None,
        source: Provenance | None = None,
    ) -> Fact:
        source_stored = self._normalize_provenance(source)
        about_resolved = self.store.resolve_alias(about)

        fact_id_val = fact_id(
            about_resolved,
            predicate,
            value,
            source_stored.at,
            source_stored.kind.value,
            source_stored.url or "",
        )
        if fact_id_val in self.store.state.facts:
            return self.store.state.facts[fact_id_val]

        fact = Fact(
            id=fact_id_val,
            about=about_resolved,
            predicate=predicate,
            value=value,
            confidence=confidence,
            context=context,
            source=source_stored,
            asserted_at=source_stored.at,
        )

        # Conflict resolution
        policy = self.opts.conflict_policy
        rivals = [
            f for f in self.store.state.facts.values()
            if f.about == about_resolved and f.predicate == predicate and not f.superseded_by
        ]
        winner = fact
        for rival in rivals:
            rival_wins = False
            if policy == ConflictPolicy.HIGHEST_CONFIDENCE_WINS:
                rival_wins = rival.confidence > winner.confidence
            elif policy == ConflictPolicy.SOURCE_PRIORITY:
                rival_priority = self._priority_of(rival.source.kind.value)
                winner_priority = self._priority_of(winner.source.kind.value)
                rival_wins = rival_priority < winner_priority
            else:  # most-recent-wins
                rival_wins = rival.asserted_at > winner.asserted_at

            if rival_wins:
                winner = rival

        event = self.store.append("assertFact", fact, source_stored.at)

        for f in [fact, *rivals]:
            if f.id != winner.id:
                self.store.state.facts[f.id].superseded_by = winner.id

        # Ensure subject entity exists
        if about_resolved not in self.store.state.entities:
            inferred_type = about_resolved.split(":")[0] if ":" in about_resolved else "entity"
            self.store.append("upsertEntity", Entity(
                type=inferred_type,
                id=about_resolved,
                attrs={},
                schema_version=1,
                source=source_stored,
                created_at=source_stored.at,
                updated_at=source_stored.at,
                aliases=[],
                state=EntityState.EMERGING,
            ), source_stored.at)

        entity = self.store.state.entities[about_resolved]
        entity.attrs[predicate] = winner.value
        entity.updated_at = source_stored.at

        self.store.log_audit("assertFact", source_stored.by or "system",
                           f"{about_resolved}.{predicate} = {winner.value} ({policy})",
                           event.id, source_stored.run_id, source_stored.at)
        self.store.persist()

        return self.store.state.facts[fact_id_val]

    def _priority_of(self, kind: str) -> int:
        """Get priority of a provenance kind."""
        ranking = self.opts.source_priority or []
        try:
            return ranking.index(kind)
        except ValueError:
            return 1000  # low priority for unknown kinds

    # ---------------------------------------------------------------- ingest

    async def ingest(self, observations: list[IngestObservation]) -> IngestReport:
        """Run the ingest pipeline on observations."""
        return await self._enqueue(lambda: self._ingest_processor.process_batch(observations))

    # ---------------------------------------------------------------- reads

    def view(self, name: str):
        """Get a view on the world state."""
        if name == "graph":
            return GraphView(self.store)
        elif name == "facts":
            return FactsView(self.store)
        elif name == "snapshot":
            return SnapshotView(self.store)
        elif name == "timeline":
            return TimelineView(self.store)
        else:
            raise ValueError(f"World Model: unknown view '{name}'")

    def register_view(self, name: str, spec: Any) -> None:
        """Register a custom view."""
        # Not implemented yet
        pass

    # ------------------------------------------------------------- operator

    def merge_queue(self) -> list[MergeProposal]:
        """Get the merge proposal queue."""
        return list(self.store.state.merge_queue)

    async def approve_merge(self, proposal_id: str, by: str) -> None:
        """Approve a merge proposal."""
        await self._enqueue(lambda: self._approve_merge_sync(proposal_id, by))

    def _approve_merge_sync(self, proposal_id: str, by: str) -> None:
        p = next(
            (
                m
                for m in self.store.state.merge_queue
                if m.id == proposal_id and m.status == "pending"
            ),
            None,
        )
        if not p:
            raise ValueError(f"World Model: no pending merge proposal {proposal_id}")

        at = self.clock().isoformat()
        p.status = "approved"
        p.resolved_at = at
        p.resolved_by = by

        self.store.append("alias", {
            "aliasId": p.left_id,
            "primaryId": p.right_id,
            "mergedAt": at,
            "mergedBy": by,
            "reason": p.reason,
        }, at)
        self.store.log_audit("merge-approved", by, f"{p.left_name} -> {p.right_name}", None, None, at)

    async def reject_merge(self, proposal_id: str, by: str) -> None:
        """Reject a merge proposal."""
        await self._enqueue(lambda: self._reject_merge_sync(proposal_id, by))

    def _reject_merge_sync(self, proposal_id: str, by: str) -> None:
        p = next(
            (
                m
                for m in self.store.state.merge_queue
                if m.id == proposal_id and m.status == "pending"
            ),
            None,
        )
        if not p:
            raise ValueError(f"World Model: no pending merge proposal {proposal_id}")

        p.status = "rejected"
        p.resolved_at = self.clock().isoformat()
        p.resolved_by = by
        self.store.log_audit("merge-rejected", by, f"{p.left_name} stays separate from {p.right_name}")
        self.store.persist()

    def audit(self) -> list[AuditEntry]:
        """Get audit log."""
        return list(self.store.audit)

    def events(self) -> list[WorldEvent]:
        """Get all events."""
        return list(self.store.events)

    def state_shape(self) -> dict[str, Any]:
        """Get the full state shape."""
        return store_world_state_shape(self.store)

    def state_shape_canonical(self) -> str:
        """Get canonical JSON of state shape for comparison."""
        return canonical_json(self.state_shape())

    def subscribe_events(self, fn: Callable[[WorldEvent], None]) -> Callable[[], None]:
        """Subscribe to new events."""
        return self.store.subscribe(fn)


# ---------------------------------------------------------------- views

class GraphView:
    def __init__(self, store: EventStore):
        self.store = store

    def entity(self, id: str) -> Entity | None:
        return self.store.state.entities.get(self.store.resolve_alias(id))

    def neighbors_of(
        self,
        id: str,
        via: str | None = None,
        in_context: str | None = None,
        at: str | None = None,
    ) -> list[Entity]:
        rid = self.store.resolve_alias(id)
        out: list[Entity] = []

        for rel in self.store.state.relationships.values():
            if via and rel.type != via:
                continue
            if in_context and rel.context != in_context:
                continue
            if at and not self._valid_at(rel, at):
                continue
            if not at and rel.valid_to:
                continue

            other = rel.to if rel.from_ == rid else rel.from_ if rel.to == rid else None
            if not other:
                continue

            entity = self.store.state.entities.get(other)
            if entity:
                out.append(entity)

        return sorted(out, key=lambda e: e.id)

    def incoming(self, id: str, via: str | None = None) -> list[Entity]:
        rid = self.store.resolve_alias(id)
        out: list[Entity] = []

        for rel in self.store.state.relationships.values():
            if rel.to != rid:
                continue
            if via and rel.type != via:
                continue
            if rel.valid_to:
                continue

            entity = self.store.state.entities.get(rel.from_)
            if entity:
                out.append(entity)

        return sorted(out, key=lambda e: e.id)

    def entities_in_context(self, context_id: str, type: str | None = None) -> list[Entity]:
        seen: dict[str, Entity] = {}
        for rel in self.store.state.relationships.values():
            if rel.context != context_id:
                continue
            for eid in [rel.from_, rel.to]:
                entity = self.store.state.entities.get(eid)
                if entity and (type is None or entity.type == type):
                    seen[entity.id] = entity
        return sorted(seen.values(), key=lambda e: e.id)

    def traverse(
        self,
        start_id: str,
        via: str,
        direction: str,
        max_depth: int = 5,
    ) -> list[Entity]:
        out: list[Entity] = []
        visited: set[str] = set()
        frontier = [self.store.resolve_alias(start_id)]

        for _depth in range(max_depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for id in frontier:
                for rel in self.store.state.relationships.values():
                    if rel.type != via or rel.valid_to:
                        continue
                    target = None
                    if direction == "ancestors" and rel.from_ == id:
                        target = rel.to
                    elif direction == "descendants" and rel.to == id:
                        target = rel.from_

                    if target and target not in visited:
                        visited.add(target)
                        entity = self.store.state.entities.get(target)
                        if entity:
                            out.append(entity)
                        next_frontier.append(target)
            frontier = next_frontier

        return out

    def query(self, type: str | None = None, where: Callable[[Entity], bool] | None = None) -> list[Entity]:
        result = list(self.store.state.entities.values())
        if type:
            result = [e for e in result if e.type == type]
        if where:
            result = [e for e in result if where(e)]
        return sorted(result, key=lambda e: e.id)

    def _valid_at(self, rel: Relationship, at: str) -> bool:
        if rel.valid_from and at < rel.valid_from:
            return False
        return not (rel.valid_to and at >= rel.valid_to)


class FactsView:
    def __init__(self, store: EventStore):
        self.store = store

    def about(self, id: str) -> list[Fact]:
        rid = self.store.resolve_alias(id)
        return sorted(
            [f for f in self.store.state.facts.values() if f.about == rid],
            key=lambda f: f.asserted_at,
        )


class SnapshotView:
    def __init__(self, store: EventStore):
        self.store = store

    def entity_at(self, id: str, at: str) -> Entity | None:
        iso = at if len(at) > 10 else f"{at}T23:59:59.999Z"
        state = self.store.fold_until(iso)
        cur = id
        seen = set()
        while cur in state.aliases and cur not in seen:
            seen.add(cur)
            cur = state.aliases[cur]
        return state.entities.get(cur)


class TimelineView:
    def __init__(self, store: EventStore):
        self.store = store

    def subscribe(self, fn: Callable[[WorldEvent], None]) -> Callable[[], None]:
        return self.store.subscribe(fn)

    def get(self) -> list[WorldEvent]:
        return list(self.store.events)


# ---------------------------------------------------------------- conformance exports

__all__ = [
    "AuditEntry",
    "ConflictPolicy",
    "Context",
    "Entity",
    "EntityState",
    "Fact",
    "IngestEntity",
    "IngestObservation",
    "IngestReport",
    "MergeDecision",
    "MergeProposal",
    "Provenance",
    "ProvenanceKind",
    "Relationship",
    "StoredProvenance",
    "WorldEvent",
    "WorldModel",
    "WorldModelOptions",
    "canonical_json",
    "context_id_from_attrs",
    "decide",
    "entity_id_from_name",
    "external_id",
    "fact_id",
    "jaccard",
    "levenshtein",
    "name_similarity",
    "normalize_name",
    "relationship_id",
    "sha256_hex",
    "world_state_shape",
]
