"""The World Model store: a folded snapshot of entities with stable IDs, optional file persistence.

The TypeScript reference is event-sourced; this Python store keeps the folded state in memory and snapshots
it as one JSON file, so one worker process shares it with the UI and the CLI without a Node dependency.
Re-ingesting the same entity changes nothing (the empty-diff guarantee of the Meterless spec, D-058).
Provenance is kept next to every entity.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from barthelona.world_model.types import Provenance, WorldEntity

Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class WorldModel:
    """Shared state for a run: keyed, stable-ID entities that parallel or later drafts read back."""

    def __init__(self, path: Path | str | None = None, clock: Clock = _default_clock) -> None:
        self._path = Path(path) if path is not None else None
        self._clock = clock
        self._entities: dict[str, WorldEntity] = {}
        if self._path is not None and self._path.exists():
            self._load()

    # --- writes ---------------------------------------------------------------------------------

    def upsert(self, entity: WorldEntity) -> bool:
        """Store *entity*, merging attrs into an existing one with the same stable id.

        Returns True only when the stored state changed, so a re-ingest of identical data reports an empty
        diff. The provenance timestamp is filled from the clock when the caller left it empty.
        """
        provenance = entity.provenance
        if not provenance.at:
            provenance = replace(provenance, at=self._clock().isoformat())
        previous = self._entities.get(entity.id)
        if previous is not None and previous.kind == entity.kind:
            merged = {**previous.attrs, **entity.attrs}
            if merged == previous.attrs:
                return False  # identical data: empty diff
            entity = replace(entity, attrs=merged, provenance=provenance)
        else:
            entity = replace(entity, provenance=provenance)
        self._entities[entity.id] = entity
        self._save()
        return True

    def upsert_all(self, entities: Sequence[WorldEntity]) -> int:
        """Store every entity; the number whose state changed."""
        return sum(1 for entity in entities if self.upsert(entity))

    # --- reads ----------------------------------------------------------------------------------

    def entities(
        self,
        run_id: str | None = None,
        kind: str | None = None,
        slug: str | None = None,
    ) -> list[WorldEntity]:
        """Matching entities, sorted by kind then key, so the CLI, UI and recall agree on the order."""
        found = []
        for entity in self._entities.values():
            if run_id is not None and entity.run_id != run_id:
                continue
            if kind is not None and entity.kind != kind:
                continue
            if slug is not None and entity.slug != slug:
                continue
            found.append(entity)
        return sorted(found, key=lambda entity: (entity.kind, entity.key))

    def count(self) -> int:
        return len(self._entities)

    def close(self) -> None:
        """Flush (the file is written on each upsert, so nothing is pending) and release nothing."""

    # --- persistence ---------------------------------------------------------------------------

    def _path_for_write(self) -> Path | None:
        return self._path

    def _save(self) -> None:
        path = self._path_for_write()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        documents = [self._dump(entity) for entity in sorted(self._entities.values(), key=lambda e: e.id)]
        body = json.dumps({"entities": documents}, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        tmp.replace(path)

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # a store that cannot be read starts empty rather than crash the worker
        for document in payload.get("entities", []):
            entity = self._restore(document)
            self._entities[entity.id] = entity

    @staticmethod
    def _dump(entity: WorldEntity) -> dict[str, Any]:
        return {
            "kind": entity.kind,
            "key": entity.key,
            "attrs": entity.attrs,
            "provenance": entity.provenance.as_dict(),
        }

    @staticmethod
    def _restore(document: dict[str, Any]) -> WorldEntity:
        provenance = document.get("provenance") or {}
        return WorldEntity(
            kind=document["kind"],
            key=document["key"],
            attrs=document.get("attrs") or {},
            provenance=Provenance(
                kind=provenance.get("kind", "barthelona"),
                at=provenance.get("at", ""),
                by=provenance.get("by"),
                route=provenance.get("route", ""),
                run_id=provenance.get("run_id"),
            ),
        )


def format_entities(entities: Sequence[WorldEntity]) -> str:
    """One readable line per entity for the CLI, the UI and the recall block (D-058)."""
    lines: list[str] = []
    for entity in entities:
        attrs = dict(entity.attrs)
        run = attrs.pop("run_id", entity.run_id or "-")
        attrs.pop("slug", entity.slug or "")  # the key already names it
        attrs.pop("id", None)
        details = ", ".join(f"{key}={value!r}" for key, value in attrs.items())
        by = entity.provenance.by or "?"
        route = entity.provenance.route or "?"
        lines.append(f"- {entity.kind} {entity.key}: {details} (run {run}, route {route}, model {by})")
    return "\n".join(lines)
