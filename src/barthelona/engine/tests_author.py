"""`test_author` and `validate_spec` (docs/architecture.md §6.1 step 4): acceptance tests before gate G1.

The author writes golden I/O cases for the spec's requirements; the check that every requirement has at least
one test is deterministic and runs twice: inside the model loop (so the model is told what is uncovered) and
as the `validate_spec` node. A reference model and the emulator cross-check of the examples are not built yet.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain import (
    Expectation,
    Level,
    ProjectSpec,
    Requirement,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.domain._base import DomainModel, ItemId, ShortText, require_unique
from barthelona.engine.spec import OnCall, ask_json, with_facts
from barthelona.llm.gateway import ModelGateway

TEST_ROLE = "worker"  # the non-thinking lane: reasoning ate the output budget on long outputs (#257)

_PROMPT = """You write acceptance tests for an assembly-language program from its specification.
Answer with ONE JSON object and nothing else:
{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": "", "stdout": "1\\n2\\n3\\n",
            "exit_code": 0},
           {"id": "T2", "requirement_ids": ["R2"], "stdin": "y\\n", "stdout_contains": ["Total: 6\\n"],
            "exit_code": 0}]}
That example only shows the shape; the values come from the specification.
Rules: every requirement id is covered by at least one test; a requirement the output cannot show (such as
which syscalls are used) is listed in "requirement_ids" of the test that exercises the program most fully, and
only ids that appear in the requirements are used. Give "stdout" (the exact text, use \\n for
newlines) only when the specification fixes the whole output. When the program prints free text, such as
prompts or messages, give "stdout_contains" instead: short texts that the output must hold, taken from the
requirements (scores, result words, formats); end a fixed value with the newline that follows it, so that
"Score: 2" cannot match "Score: 20". Never invent text the requirements do not give, such as the
wording of prompts. Pick inputs whose result is easy to count (all yes, all no, alternating) and work every
expected value out from the rules, one step at a time, before you write it. Each test has "stdout" or
"stdout_contains". At most 20 tests; keep them short; no code."""

# An exact expected output longer than this cannot be fixed by a specification: it holds invented text (#259).
MAX_EXACT_STDOUT = 200


class TestDraft(DomainModel):
    __test__ = False

    id: ItemId
    requirement_ids: list[ItemId] = Field(min_length=1, max_length=32)
    stdin: Annotated[str, StringConstraints(max_length=4000)] = ""
    stdout: Annotated[str, StringConstraints(max_length=4000)] | None = None
    stdout_contains: list[ShortText] = Field(default_factory=list, max_length=16)
    exit_code: int = Field(default=0, ge=0, le=255)

    @model_validator(mode="after")
    def _checks_the_output(self) -> TestDraft:
        if self.stdout is None and not self.stdout_contains:
            raise ValueError(f"test {self.id} checks no output: give stdout or stdout_contains")
        if self.stdout is not None and self.stdout_contains:
            raise ValueError(f"test {self.id} gives both stdout and stdout_contains: give only one")
        return self


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
    long_exact = [t.id for t in draft.tests if t.stdout is not None and len(t.stdout) > MAX_EXACT_STDOUT]
    if long_exact:
        return (
            f"test {', '.join(long_exact)} pins more than {MAX_EXACT_STDOUT} characters of stdout, "
            'which the specification does not fix: give "stdout_contains" with the result lines instead'
        )
    covered = {rid for t in draft.tests for rid in t.requirement_ids}
    missing = [r.id for r in spec.requirements if r.id not in covered]
    if missing:
        ids = ", ".join(missing)
        return (
            f"no test covers requirement {ids}: add {ids} to the requirement_ids of a test; "
            "a requirement the output cannot show is covered by any test that runs the whole program"
        )
    return None


async def author_tests(
    gateway: ModelGateway, spec: ProjectSpec, facts: str, on_call: OnCall
) -> tuple[ProjectSpec, list[TestCase]]:
    """The spec with each requirement linked to its tests, and the golden I/O test cases."""
    requirements = "\n".join(f"{r.id}: {r.text}" for r in spec.requirements)
    user = (
        f"Request (authoritative: when it lists the tests, write exactly those):\n{spec.request_original}\n\n"
        f"Program: {spec.summary_en}\nRequirements:\n{requirements}"
    )
    draft = await ask_json(
        gateway,
        TEST_ROLE,
        _PROMPT,
        with_facts(user, facts),
        TestsDraft,
        on_call,
        check=lambda d: problems(spec, d),
    )
    cases = [
        TestCase(
            id=t.id,
            kind=TestKind.IO_GOLDEN,
            level=Level.V6,
            inputs={"stdin": t.stdin},
            expect=Expectation(stdout=t.stdout, stdout_contains=t.stdout_contains, exit_code=t.exit_code),
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
