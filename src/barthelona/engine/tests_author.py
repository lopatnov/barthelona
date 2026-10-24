"""`test_author` and `validate_spec` (docs/architecture.md §6.1 step 4): acceptance tests before gate G1.

The author writes golden I/O cases for the spec's requirements; the check that every requirement has at least
one test is deterministic and runs twice: inside the model loop (so the model is told what is uncovered) and
as the `validate_spec` node. A reference model and the emulator cross-check of the examples are not built yet.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from barthelona.domain import (
    Expectation,
    Level,
    ProjectSpec,
    Requirement,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.domain._base import DomainModel, ItemId, require_unique
from barthelona.engine.spec import OnCall, ask_json
from barthelona.llm.gateway import ModelGateway

TEST_ROLE = "planner"

_PROMPT = """You write acceptance tests for an assembly-language program from its specification.
Answer with ONE JSON object and nothing else:
{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": "", "stdout": "<exact expected stdout>",
            "exit_code": 0}]}
Rules: every requirement id is covered by at least one test; stdout is the exact text the program prints
(use \\n for newlines); at most 20 tests; no code."""


class TestDraft(DomainModel):
    __test__ = False

    id: ItemId
    requirement_ids: list[ItemId] = Field(min_length=1, max_length=32)
    stdin: Annotated[str, StringConstraints(max_length=4000)] = ""
    stdout: Annotated[str, StringConstraints(max_length=4000)]
    exit_code: int = Field(default=0, ge=0, le=255)


class TestsDraft(DomainModel):
    __test__ = False

    tests: list[TestDraft] = Field(min_length=1, max_length=20)


def problems(spec: ProjectSpec, draft: TestsDraft) -> str | None:
    """What is wrong with *draft* for *spec*, or None: duplicate ids, unknown or uncovered requirements."""
    try:
        require_unique("test id", [t.id for t in draft.tests])
    except ValueError as exc:
        return str(exc)
    known = {r.id for r in spec.requirements}
    unknown = sorted({rid for t in draft.tests for rid in t.requirement_ids} - known)
    if unknown:
        return f"tests name requirements that do not exist: {', '.join(unknown)}"
    covered = {rid for t in draft.tests for rid in t.requirement_ids}
    missing = [r.id for r in spec.requirements if r.id not in covered]
    if missing:
        return f"no test covers requirement {', '.join(missing)}"
    return None


async def author_tests(
    gateway: ModelGateway, spec: ProjectSpec, on_call: OnCall
) -> tuple[ProjectSpec, list[TestCase]]:
    """The spec with each requirement linked to its tests, and the golden I/O test cases."""
    requirements = "\n".join(f"{r.id}: {r.text}" for r in spec.requirements)
    user = f"Program: {spec.summary_en}\nRequirements:\n{requirements}"
    draft = await ask_json(
        gateway, TEST_ROLE, _PROMPT, user, TestsDraft, on_call, check=lambda d: problems(spec, d)
    )
    cases = [
        TestCase(
            id=t.id,
            kind=TestKind.IO_GOLDEN,
            level=Level.V6,
            inputs={"stdin": t.stdin},
            expect=Expectation(stdout=t.stdout, exit_code=t.exit_code),
            origin=TestOrigin.TEST_AUTHOR,
        )
        for t in draft.tests
    ]
    linked = [
        Requirement(id=r.id, text=r.text, test_ids=[t.id for t in draft.tests if r.id in t.requirement_ids])
        for r in spec.requirements
    ]
    return ProjectSpec.model_validate(spec.model_dump() | {"requirements": linked}), cases


def validate_spec(spec: ProjectSpec, cases: list[TestCase]) -> str | None:
    """The deterministic G1 check: every requirement lists at least one test that exists."""
    ids = {c.id for c in cases}
    for requirement in spec.requirements:
        if not requirement.test_ids or not set(requirement.test_ids) <= ids:
            return f"requirement {requirement.id} has no test"
    return None
