"""The World Model as shared state for a run (D-058).

Entities with stable IDs (requirement, test, run, attempt) record what a run produced, with provenance, so
parallel or later drafts plan from the same facts. The worker writes them as the run goes; the CLI and the UI
read the same file-backed store.
"""

from barthelona.world_model.model import WorldModel, format_entities
from barthelona.world_model.record import record_attempt, record_run_stop, record_spec_and_tests
from barthelona.world_model.types import (
    ATTEMPT,
    DEFAULT_STORE,
    REQUIREMENT,
    RUN,
    SYSTEM,
    TEST,
    Provenance,
    WorldEntity,
    attempt_key,
    case_key,
    external_id,
    requirement_key,
    run_key,
)

__all__ = [
    "ATTEMPT",
    "DEFAULT_STORE",
    "REQUIREMENT",
    "RUN",
    "SYSTEM",
    "TEST",
    "Provenance",
    "WorldEntity",
    "WorldModel",
    "attempt_key",
    "case_key",
    "external_id",
    "format_entities",
    "record_attempt",
    "record_run_stop",
    "record_spec_and_tests",
    "requirement_key",
    "run_key",
]
