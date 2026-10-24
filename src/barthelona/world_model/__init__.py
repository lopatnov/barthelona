"""World Model - Event-sourced shared state for agents.

This module implements the Meterless World Model specification:
- Event-sourced, deterministic storage
- Stable IDs derived from content
- Single-writer discipline for concurrency
- Idempotent ingest pipeline
- Conformance with the Meterless specification
"""

from .world_model import (
    WorldModel,
    WorldModelOptions,
    Entity,
    Context,
    Relationship,
    Fact,
    IngestObservation,
    IngestEntity,
    IngestReport,
    Provenance,
    ProvenanceKind,
    StoredProvenance,
    EntityState,
    MergeProposal,
    AuditEntry,
    WorldEvent,
    MergeDecision,
    ConflictPolicy,
    normalize_name,
    entity_id_from_name,
    external_id,
    context_id_from_attrs,
    fact_id,
    relationship_id,
    sha256_hex,
    canonical_json,
    levenshtein,
    name_similarity,
    jaccard,
    decide,
    world_state_shape,
)

__all__ = [
    "WorldModel",
    "WorldModelOptions",
    "Entity",
    "Context",
    "Relationship",
    "Fact",
    "IngestObservation",
    "IngestEntity",
    "IngestReport",
    "Provenance",
    "ProvenanceKind",
    "StoredProvenance",
    "EntityState",
    "MergeProposal",
    "AuditEntry",
    "WorldEvent",
    "MergeDecision",
    "ConflictPolicy",
    "normalize_name",
    "entity_id_from_name",
    "external_id",
    "context_id_from_attrs",
    "fact_id",
    "relationship_id",
    "sha256_hex",
    "canonical_json",
    "levenshtein",
    "name_similarity",
    "jaccard",
    "decide",
    "world_state_shape",
]

__version__ = "0.1.0"