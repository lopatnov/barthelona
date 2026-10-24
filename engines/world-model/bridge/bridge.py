#!/usr/bin/env python3
"""Python bridge for TypeScript World Model conformance runner.

This script receives JSON commands via a file argument and returns JSON responses via stdout.
It maintains a persistent WorldModel instance per namespace (for memory storage).
For file storage, it creates a new WorldModel each time which loads from the file.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from typing import Any, Optional

from barthelona.world_model import (
    WorldModel,
    WorldModelOptions,
    Provenance,
    ProvenanceKind,
    IngestObservation,
    IngestEntity,
    EntityState,
)


# Global store for WorldModel instances by namespace (only for memory storage)
_models: dict[str, WorldModel] = {}


def _parse_provenance(data: dict[str, Any] | None) -> Provenance | None:
    """Parse provenance from JSON."""
    if not data:
        return None
    
    kind_str = data.get("kind", "manual")
    try:
        kind = ProvenanceKind(kind_str)
    except ValueError:
        kind = ProvenanceKind.MANUAL
    
    at = data.get("at")
    if isinstance(at, str):
        at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    elif at is None:
        at = datetime.now()
    
    return Provenance(
        kind=kind,
        at=at,
        by=data.get("by"),
        run_id=data.get("run_id"),
        url=data.get("url"),
    )


def _format_provenance(prov: Any) -> dict[str, Any]:
    """Format provenance for JSON."""
    if not prov:
        return {}
    
    return {
        "kind": prov.kind.value if hasattr(prov.kind, "value") else str(prov.kind),
        "at": prov.at if isinstance(prov.at, str) else prov.at.isoformat() if hasattr(prov.at, "isoformat") else str(prov.at),
        "by": prov.by,
        "run_id": prov.run_id,
        "url": prov.url,
    }


def _format_entity(entity: Any) -> dict[str, Any]:
    """Format entity for JSON."""
    return {
        "id": entity.id,
        "type": entity.type,
        "attrs": entity.attrs,
        "name": entity.name,
        "aliases": entity.aliases,
        "state": entity.state.value if hasattr(entity.state, "value") else str(entity.state),
        "source": _format_provenance(entity.source),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


def _format_context(context: Any) -> dict[str, Any]:
    """Format context for JSON."""
    return {
        "id": context.id,
        "type": context.type,
        "attrs": context.attrs,
        "parent": context.parent,
        "source": _format_provenance(context.source),
        "created_at": context.created_at,
        "updated_at": context.updated_at,
    }


def _format_relationship(rel: Any) -> dict[str, Any]:
    """Format relationship for JSON."""
    return {
        "id": rel.id,
        "from": rel.from_,
        "type": rel.type,
        "to": rel.to,
        "context": rel.context,
        "attrs": rel.attrs,
        "valid_from": rel.valid_from,
        "valid_to": rel.valid_to,
        "source": _format_provenance(rel.source),
        "created_at": rel.created_at,
    }


def _format_audit_entry(entry: Any) -> dict[str, Any]:
    """Format audit entry for JSON."""
    return {
        "seq": entry.seq,
        "action": entry.action,
        "by": entry.by,
        "detail": entry.detail,
        "event_id": entry.event_id,
        "run_id": entry.run_id,
        "at": entry.at,
    }


def _format_event(event: Any) -> dict[str, Any]:
    """Format world event for JSON."""
    return {
        "id": event.id,
        "kind": event.kind,
        "payload": event.payload,
        "at": event.at,
        "seq": event.seq,
    }


def _get_or_create_model(args: dict[str, Any]) -> WorldModel:
    """Get existing model or create a new one.
    
    For file storage, always create a new model (which loads from file).
    For memory storage, use the cached model.
    """
    namespace = args.get("namespace")
    if not namespace:
        raise ValueError("namespace is required")
    
    storage = args.get("storage", "memory")
    
    # For file storage, always create new (loads from file)
    if storage == "file":
        opts = WorldModelOptions(
            namespace=namespace,
            storage=storage,
            directory=args.get("directory"),
            conflict_policy=args.get("conflict_policy", "most-recent-wins"),
            source_priority=args.get("source_priority"),
            resolver_auto_merge_at=args.get("resolver_auto_merge_at", 0.85),
            resolver_review_band=tuple(args.get("resolver_review_band", [0.82, 0.85])),
            clock=None,
        )
        return WorldModel(opts)
    
    # For memory storage, use cache
    if namespace in _models:
        return _models[namespace]
    
    opts = WorldModelOptions(
        namespace=namespace,
        storage=storage,
        directory=args.get("directory"),
        conflict_policy=args.get("conflict_policy", "most-recent-wins"),
        source_priority=args.get("source_priority"),
        resolver_auto_merge_at=args.get("resolver_auto_merge_at", 0.85),
        resolver_review_band=tuple(args.get("resolver_review_band", [0.82, 0.85])),
        clock=None,
    )
    
    model = WorldModel(opts)
    _models[namespace] = model
    return model


async def handle_init(args: dict[str, Any]) -> dict[str, Any]:
    """Initialize a WorldModel instance."""
    namespace = args.get("namespace")
    if not namespace:
        return {"error": "namespace is required"}
    
    # Just ensure the model can be created
    try:
        _get_or_create_model(args)
        return {"result": "initialized"}
    except Exception as e:
        return {"error": str(e)}


async def handle_upsert_entity(args: dict[str, Any]) -> dict[str, Any]:
    """Upsert an entity."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    source = _parse_provenance(args.get("source"))
    if not source:
        return {"error": "source (provenance) is required"}
    
    entity = await world.upsert_entity(
        type=args.get("type"),
        external_key=args.get("externalKey"),
        name=args.get("name"),
        attrs=args.get("attrs"),
        source=source,
        state=EntityState(args.get("state")) if args.get("state") else EntityState.ACTIVE,
    )
    
    return {"result": _format_entity(entity)}


async def handle_upsert_context(args: dict[str, Any]) -> dict[str, Any]:
    """Upsert a context."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    source = _parse_provenance(args.get("source"))
    if not source:
        return {"error": "source (provenance) is required"}
    
    context = await world.upsert_context(
        type=args.get("type"),
        external_key=args.get("externalKey"),
        attrs=args.get("attrs"),
        parent=args.get("parent"),
        source=source,
    )
    
    return {"result": _format_context(context)}


async def handle_relate(args: dict[str, Any]) -> dict[str, Any]:
    """Create a relationship."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    source = _parse_provenance(args.get("source"))
    if not source:
        return {"error": "source (provenance) is required"}
    
    rel = await world.relate(
        from_=args.get("from"),
        type=args.get("type"),
        to=args.get("to"),
        context=args.get("context"),
        attrs=args.get("attrs"),
        valid_from=args.get("validFrom"),
        valid_to=args.get("validTo"),
        source=source,
    )
    
    return {"result": {"id": rel.id}}


async def handle_assert_fact(args: dict[str, Any]) -> dict[str, Any]:
    """Assert a fact."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    source = _parse_provenance(args.get("source"))
    if not source:
        return {"error": "source (provenance) is required"}
    
    fact = await world.assert_fact(
        about=args.get("about"),
        predicate=args.get("predicate"),
        value=args.get("value"),
        confidence=args.get("confidence", 0.5),
        context=args.get("context"),
        source=source,
    )
    
    return {"result": {"id": fact.id}}


async def handle_ingest(args: dict[str, Any]) -> dict[str, Any]:
    """Run the ingest pipeline."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    observations = []
    for obs_data in args.get("observations", []):
        source = _parse_provenance(obs_data.get("source"))
        if not source:
            return {"error": "each observation must have a source (provenance)"}
        
        entities = [
            IngestEntity(type=e.get("type"), name=e.get("name"))
            for e in obs_data.get("entities", [])
        ]
        
        observations.append(IngestObservation(
            external_id=obs_data.get("externalId"),
            title=obs_data.get("title"),
            at=obs_data.get("at"),
            source=source,
            type=obs_data.get("type"),
            text=obs_data.get("text"),
            entities=entities,
        ))
    
    report = await world.ingest(observations)
    
    return {
        "result": {
            "processed": report.processed,
            "clusters": report.clusters,
            "changed": report.changed,
            "skipped_unchanged": report.skipped_unchanged,
        }
    }


def handle_state_shape(args: dict[str, Any]) -> dict[str, Any]:
    """Get the canonical state shape."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    shape = world.state_shape()
    
    return {"result": shape}


async def handle_neighbors_of(args: dict[str, Any]) -> dict[str, Any]:
    """Get neighbors of an entity."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    graph = world.view("graph")
    
    neighbors = graph.neighbors_of(
        id=args.get("id"),
        via=args.get("via"),
        in_context=args.get("in_context"),
        at=args.get("at"),
    )
    
    return {"result": [_format_entity(e) for e in neighbors]}


async def handle_incoming(args: dict[str, Any]) -> dict[str, Any]:
    """Get incoming relationships."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    graph = world.view("graph")
    
    incoming = graph.incoming(
        id=args.get("id"),
        via=args.get("via"),
    )
    
    return {"result": [_format_entity(e) for e in incoming]}


def handle_audit(args: dict[str, Any]) -> dict[str, Any]:
    """Get audit log."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    audit = world.audit()
    
    return {"result": [_format_audit_entry(e) for e in audit]}


def handle_events(args: dict[str, Any]) -> dict[str, Any]:
    """Get all events."""
    try:
        world = _get_or_create_model(args)
    except Exception as e:
        return {"error": str(e)}
    
    events = world.events()
    
    return {"result": [_format_event(e) for e in events]}


async def main():
    """Main entry point."""
    try:
        # Read JSON from file argument
        if len(sys.argv) < 2:
            print(json.dumps({"error": "no input file provided"}))
            return
        
        input_file = sys.argv[1]
        with open(input_file, 'r') as f:
            input_data = f.read().strip()
        
        if not input_data:
            print(json.dumps({"error": "empty input"}))
            return
        
        request = json.loads(input_data)
        method = request.get("method")
        args = request.get("args", {})
        
        # Handle the request
        result = None
        if method == "init":
            result = await handle_init(args)
        elif method == "upsert_entity":
            result = await handle_upsert_entity(args)
        elif method == "upsert_context":
            result = await handle_upsert_context(args)
        elif method == "relate":
            result = await handle_relate(args)
        elif method == "assert_fact":
            result = await handle_assert_fact(args)
        elif method == "ingest":
            result = await handle_ingest(args)
        elif method == "state_shape":
            result = handle_state_shape(args)
        elif method == "neighbors_of":
            result = await handle_neighbors_of(args)
        elif method == "incoming":
            result = await handle_incoming(args)
        elif method == "audit":
            result = handle_audit(args)
        elif method == "events":
            result = handle_events(args)
        else:
            result = {"error": f"unknown method: {method}"}
        
        print(json.dumps(result, separators=(",", ":")))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}, separators=(",", ":")))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())