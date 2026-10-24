"""World Model - Event-sourced shared state for agents.

This module implements the Meterless World Model specification:
- Event-sourced, deterministic storage
- Stable IDs derived from content
- Single-writer discipline for concurrency
- Idempotent ingest pipeline
- Conformance with the Meterless specification
"""

from .world_model import (
    AuditEntry,
    ConflictPolicy,
    Context,
    Entity,
    EntityState,
    Fact,
    IngestEntity,
    IngestObservation,
    IngestReport,
    MergeDecision,
    MergeProposal,
    Provenance,
    ProvenanceKind,
    Relationship,
    StoredProvenance,
    WorldEvent,
    WorldModel,
    WorldModelOptions,
    canonical_json,
    context_id_from_attrs,
    decide,
    entity_id_from_name,
    external_id,
    fact_id,
    jaccard,
    levenshtein,
    name_similarity,
    normalize_name,
    relationship_id,
    sha256_hex,
    world_state_shape,
)

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

__version__ = "0.1.0"
