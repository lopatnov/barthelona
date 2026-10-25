"""What a run records in the World Model, as pure functions over the domain models (D-058).

The graph nodes and the worker call these at the moments the issue names: spec and tests after
`validate_spec`, each attempt after the oracles judge it, and the stop reason at the end. Keeping them here,
outside the engine, lets the unit tests exercise the wiring with an in-memory World Model and no Node, NASM or
emulator.
"""

from __future__ import annotations

from collections.abc import Sequence

from barthelona.domain import ProjectSpec, TestCase
from barthelona.world_model.types import (
    ATTEMPT,
    REQUIREMENT,
    RUN,
    TEST,
    Provenance,
    WorldEntity,
    attempt_key,
    case_key,
    requirement_key,
    run_key,
)


def record_spec_and_tests(
    run_id: str,
    spec: ProjectSpec,
    cases: Sequence[TestCase],
    spec_model: str | None,
    test_model: str | None,
) -> list[WorldEntity]:
    """The run, requirement and test entities written once `validate_spec` has accepted the spec."""
    slug = spec.slug
    entities = [
        WorldEntity(
            kind=RUN,
            key=run_key(run_id),
            attrs={
                "run_id": run_id,
                "slug": slug,
                "summary": spec.summary_en,
                "preset": spec.target.preset,
            },
            provenance=Provenance(by=spec_model, route="planner", run_id=run_id),
        )
    ]
    entities.extend(
        WorldEntity(
            kind=REQUIREMENT,
            key=requirement_key(run_id, requirement.id),
            attrs={
                "run_id": run_id,
                "slug": slug,
                "id": requirement.id,
                "text": requirement.text,
                "test_ids": list(requirement.test_ids),
            },
            provenance=Provenance(by=spec_model, route="planner", run_id=run_id),
        )
        for requirement in spec.requirements
    )
    entities.extend(
        WorldEntity(
            kind=TEST,
            key=case_key(run_id, case.id),
            attrs={
                "run_id": run_id,
                "slug": slug,
                "id": case.id,
                "stdin": str(case.inputs.get("stdin", "")),
                "stdout": case.expect.stdout,
                "stdout_contains": list(case.expect.stdout_contains),
                "exit_code": case.expect.exit_code,
                "requirement_ids": sorted(r.id for r in spec.requirements if case.id in r.test_ids),
            },
            provenance=Provenance(by=test_model, route="worker", run_id=run_id),
        )
        for case in cases
    )
    return entities


def record_attempt(
    run_id: str,
    slug: str,
    index: int,
    verdict: str,
    errors: Sequence[str],
    chunks: int,
    model: str | None,
    route: str,
) -> WorldEntity:
    """One judged attempt: its verdict, the oracle's errors and the work it took."""
    return WorldEntity(
        kind=ATTEMPT,
        key=attempt_key(run_id, index),
        attrs={
            "run_id": run_id,
            "slug": slug,
            "index": index,
            "verdict": verdict,
            "errors": list(errors),
            "chunks": chunks,
        },
        provenance=Provenance(by=model, route=route, run_id=run_id),
    )


def record_run_stop(run_id: str, stop_reason: str) -> WorldEntity:
    """The run entity's final update: the reason the run stopped, merged over its earlier attrs."""
    return WorldEntity(
        kind=RUN,
        key=run_key(run_id),
        attrs={"run_id": run_id, "stop_reason": stop_reason},
        provenance=Provenance(route="worker", run_id=run_id),
    )
