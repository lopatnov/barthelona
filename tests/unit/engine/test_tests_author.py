"""`author_tests`: golden I/O for exact output, substring expectations for free text, bounded retries."""

from __future__ import annotations

from collections.abc import Collection

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Linker,
    LLMCallRecord,
    ObjFormat,
    ProjectSpec,
    Requirement,
    RunEnv,
    TargetProfile,
)
from barthelona.engine.spec import MODELS, SpecError, ask_json
from barthelona.engine.tests_author import TEST_ROLE, TestsDraft, author_tests
from barthelona.llm import FakeGateway
from barthelona.llm.types import Completion, CompletionRequest


def _spec() -> ProjectSpec:
    target = TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=Dialect.NASM,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    return ProjectSpec(
        id="s1",
        slug="quiz",
        request_original="a quiz",
        request_lang="en",
        summary_en="Asks questions and prints a score.",
        target=target,
        requirements=[Requirement(id="R1", text="Prints 'Score: <n>'.")],
    )


_EXACT = '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": "", "stdout": "Score: 0\\n"}]}'
_CONTAINS = (
    '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": "y\\ny\\n", '
    '"stdout_contains": ["Score: 2"]}]}'
)
_NOTHING = '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": ""}]}'


async def test_a_substring_expectation_becomes_the_test_cases_stdout_contains() -> None:
    gateway = FakeGateway([_CONTAINS])
    _, cases = await author_tests(gateway, _spec(), "", lambda _r: None)
    assert cases[0].expect.stdout is None
    assert cases[0].expect.stdout_contains == ["Score: 2"]
    assert cases[0].inputs == {"stdin": "y\ny\n"}


async def test_an_exact_expectation_still_works() -> None:
    _, cases = await author_tests(FakeGateway([_EXACT]), _spec(), "", lambda _r: None)
    assert (cases[0].expect.stdout, cases[0].expect.stdout_contains) == ("Score: 0\n", [])


async def test_the_test_author_uses_the_lane_without_thinking() -> None:
    gateway = FakeGateway([_EXACT])
    await author_tests(gateway, _spec(), "", lambda _r: None)
    assert gateway.calls[0][0] == TEST_ROLE == "worker"


async def test_a_test_that_checks_no_output_is_sent_back_and_then_accepted() -> None:
    gateway = FakeGateway([_NOTHING, _CONTAINS])
    _, cases = await author_tests(gateway, _spec(), "", lambda _r: None)
    assert cases[0].expect.stdout_contains == ["Score: 2"]
    assert "checks no output" in gateway.calls[1][1].messages[-1].content


async def test_a_test_that_gives_both_forms_is_sent_back() -> None:
    both = (
        '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdout": "", "stdout_contains": ["Score: 2"]}]}'
    )
    gateway = FakeGateway([both, _CONTAINS])
    _, cases = await author_tests(gateway, _spec(), "", lambda _r: None)
    assert cases[0].expect.stdout is None
    assert "gives both stdout and stdout_contains" in gateway.calls[1][1].messages[-1].content


async def test_a_long_exact_transcript_is_sent_back_for_substring_checks() -> None:
    transcript = "Question? (y/n): " * 30
    long_exact = (
        '{"tests": [{"id": "T1", "requirement_ids": ["R1"], "stdin": "y\\n", "stdout": "'
        + transcript
        + '"}]}'
    )
    gateway = FakeGateway([long_exact, _CONTAINS])
    _, cases = await author_tests(gateway, _spec(), "", lambda _r: None)
    assert cases[0].expect.stdout_contains == ["Score: 2"]
    assert 'give "stdout_contains"' in gateway.calls[1][1].messages[-1].content


class _CutOff(FakeGateway):
    """Reports the first answer as stopped by the length limit, like a provider does."""

    async def complete(
        self, role: str, request: CompletionRequest, avoid: Collection[str] = ()
    ) -> Completion:
        done = await super().complete(role, request, avoid)
        if len(self.calls) > 1:
            return done
        record: LLMCallRecord = done.record.model_copy(update={"stop_reason": "length"})
        return done.model_copy(update={"record": record})


class _TwoLanes(FakeGateway):
    """Two models of one chain: the first answer comes from lane-1, the rest from lane-2."""

    async def complete(
        self, role: str, request: CompletionRequest, avoid: Collection[str] = ()
    ) -> Completion:
        done = await super().complete(role, request, avoid)
        lane = "lane-1" if len(self.calls) == 1 else "lane-2"
        return done.model_copy(update={"served_by": lane})


async def test_a_reply_cut_off_by_the_length_limit_is_named_as_such() -> None:
    gateway = _CutOff(['{"tests": [{"id": "T1", "requirement_ids": ["R1"], "std', _CONTAINS])
    await ask_json(gateway, "worker", "sys", "user", TestsDraft, lambda _r: None)
    assert "cut off by the length limit" in gateway.calls[1][1].messages[-1].content


async def test_a_lane_that_writes_code_is_passed_over_for_the_next_model_of_the_chain() -> None:
    gateway = _TwoLanes(["section .text\n_start:\n    mov rax, 60\n", _EXACT])
    _, cases = await author_tests(gateway, _spec(), "", lambda _r: None)
    assert cases[0].expect.stdout == "Score: 0\n"
    assert gateway.avoided == [(), ("lane-1",)]  # the model that answered code is not asked again


async def test_an_unusable_lane_stops_the_loop_once_the_chain_is_spent() -> None:
    gateway = FakeGateway(["nope"] * MODELS)
    with pytest.raises(SpecError, match="no JSON object"):
        await ask_json(gateway, "worker", "sys", "user", TestsDraft, lambda _r: None)
    assert len(gateway.calls) == MODELS
