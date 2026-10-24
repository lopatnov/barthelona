"""Ingest pipeline for World Model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .stable_ids import entity_id_from_name, external_id, relationship_id
from .store import EventStore, world_state_shape
from .types import (
    Entity,
    EntityState,
    IngestObservation,
    IngestReport,
    Provenance,
    Relationship,
    StoredProvenance,
)


@dataclass
class IngestItemResult:
    entity_id: str
    entity_ids: list[str]


def run_ingest_pipeline(
    store: EventStore,
    observations: list[IngestObservation],
    process_observation: Callable[[IngestObservation], IngestItemResult],
) -> IngestReport:
    """
    Run the ingest pipeline over a batch of observations.

    Returns a report with counts and whether state changed.
    """
    # Capture state shape before
    shape_before = world_state_shape(store)

    processed = 0
    entity_ids_seen: set[str] = set()

    for obs in observations:
        result = process_observation(obs)
        entity_ids_seen.update(result.entity_ids)
        processed += 1

    # Capture state shape after
    shape_after = world_state_shape(store)

    changed = shape_before != shape_after

    # Calculate skipped (entities that didn't change)
    skipped = 0
    if not changed:
        skipped = processed

    return IngestReport(
        processed=processed,
        clusters=0,  # Not implemented in this version
        changed=changed,
        skipped_unchanged=skipped,
    )


class IngestProcessor:
    """Processes observations through the World Model ingest pipeline."""

    def __init__(self, store: EventStore, clock: Callable[[], int]):
        self.store = store
        self.clock = clock

    def process_batch(self, observations: list[IngestObservation]) -> IngestReport:
        """Process a batch of observations through the ingest pipeline."""

        # Capture state shape before
        shape_before = world_state_shape(self.store)

        processed = 0
        for obs in observations:
            self.process_observation(obs)
            processed += 1

        # Capture state shape after
        shape_after = world_state_shape(self.store)

        changed = shape_before != shape_after

        # Calculate skipped (entities that didn't change)
        skipped = 0
        if not changed:
            skipped = processed

        return IngestReport(
            processed=processed,
            clusters=0,  # Not implemented in this version
            changed=changed,
            skipped_unchanged=skipped,
        )

    def process_observation(self, obs: IngestObservation) -> IngestItemResult:
        """Process a single observation."""
        # Normalize provenance
        source = self._normalize_provenance(obs.source)

        # Create or update the observation entity
        obs_type = obs.type or "item"
        obs_entity_id = external_id(obs_type, "ingest", obs.external_id)

        obs_entity = self._fold_entity_upsert(
            obs_entity_id,
            {
                "type": obs_type,
                "external_key": {"system": "ingest", "id": obs.external_id},
                "attrs": {"title": obs.title, "text": obs.text},
            },
            source,
            obs.title,
        )

        entity_ids: list[str] = []

        # Process mentioned entities
        for mention in obs.entities:
            mid = entity_id_from_name(mention.type, mention.name)
            self._fold_entity_upsert(
                mid,
                {"type": mention.type, "name": mention.name},
                source,
                mention.name,
            )
            resolved_mid = self.store.resolve_alias(mid)
            entity_ids.append(resolved_mid)

            # Create mentions relationship (include attrs for unique ID)
            rid = relationship_id(obs_entity.id, "mentions", resolved_mid, attrs={"mention": True})
            if rid not in self.store.state.relationships:
                relationship = Relationship(
                    id=rid,
                    from_=obs_entity.id,
                    type="mentions",
                    to=resolved_mid,
                    valid_from=source.at,
                    schema_version=1,
                    source=source,
                    created_at=source.at,
                )
                self.store.append("relate", relationship, source.at)

        return IngestItemResult(
            entity_id=obs_entity.id,
            entity_ids=sorted(entity_ids),
        )

    def _normalize_provenance(self, source: Provenance) -> StoredProvenance:
        """Normalize provenance to stored format."""
        at_iso = source.at.isoformat() if isinstance(source.at, str) is False else source.at
        return StoredProvenance(
            kind=source.kind,
            at=at_iso,
            by=source.by,
            run_id=source.run_id,
            url=source.url,
        )

    def _fold_entity_upsert(
        self,
        entity_id: str,
        input_data: dict[str, Any],
        source: StoredProvenance,
        name: str | None,
    ) -> Entity:
        """Upsert an entity into the store. Updates existing entity if present."""
        resolved_id = self.store.resolve_alias(entity_id)

        # Check if entity already exists
        existing = self.store.state.entities.get(resolved_id)
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
            self.store.append("upsertEntity", existing, source.at)
            self.store.log_audit(
                "upsertEntity",
                source.by or "system",
                f"{resolved_id} ({input_data['type']})",
                run_id=source.run_id,
                at=source.at,
            )
            return existing

        # Create new entity
        entity = Entity(
            type=input_data["type"],
            id=resolved_id,
            attrs=input_data.get("attrs", {}),
            schema_version=1,
            source=source,
            created_at=source.at,
            updated_at=source.at,
            name=name,
            aliases=[name] if name else [],
            state=EntityState.ACTIVE,
        )

        # Check for name-based resolution (near-duplicate detection)
        if "external_key" not in input_data and name:
            for other in self.store.state.entities.values():
                if other.type != input_data["type"] or other.id == resolved_id or not other.name:
                    continue
                # Import similarity function here to avoid circular import
                from .resolve import decide, name_similarity

                similarity = name_similarity(name, other.name)
                decision = decide(similarity, 0.85, (0.82, 0.85))

                if decision == "auto-merge":
                    # Create alias event
                    self.store.append(
                        "alias",
                        {
                            "aliasId": resolved_id,
                            "primaryId": other.id,
                            "mergedAt": source.at,
                            "mergedBy": "resolver",
                            "reason": f"similarity {similarity:.3f}",
                        },
                        source.at,
                    )
                    self.store.log_audit(
                        "auto-merge",
                        "resolver",
                        f"{name} -> {other.name} ({similarity:.3f})",
                        undefined=None,
                        run_id=None,
                        at=source.at,
                    )
                    # Update the other entity with new data
                    return self._update_existing_entity(other, input_data, source, name)

                elif decision == "review":
                    # Queue for review (simplified - just log)
                    self.store.log_audit(
                        "merge-proposed",
                        "resolver",
                        f"{name} ~ {other.name} ({similarity:.3f}) queued",
                        undefined=None,
                        run_id=None,
                        at=source.at,
                    )

        # Append new entity event
        self.store.append("upsertEntity", entity, source.at)
        self.store.log_audit(
            "upsertEntity",
            source.by or "system",
            f"{resolved_id} ({input_data['type']})",
            run_id=source.run_id,
            at=source.at,
        )

        return self.store.state.entities[resolved_id]

    def _update_existing_entity(
        self,
        existing: Entity,
        input_data: dict[str, Any],
        source: StoredProvenance,
        name: str | None,
    ) -> Entity:
        """Update an existing entity with new data."""
        # Merge attributes
        existing.attrs.update(input_data.get("attrs", {}))
        if name and name not in existing.aliases:
            existing.aliases.append(name)
        existing.updated_at = source.at
        existing.source = source

        # Append upsert event for the merged entity
        self.store.append("upsertEntity", existing, source.at)

        return existing
