"""`codegen`: the chunk loop writes, the oracles decide, a rejection is repaired a bounded number of times."""

from __future__ import annotations

import shutil

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Expectation,
    Level,
    Linker,
    ObjFormat,
    ProjectSpec,
    Requirement,
    RunEnv,
    StopReason,
    TargetProfile,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.engine.codegen import REPAIRS, Codegen, check_all, generate_source, task_text
from barthelona.llm import FakeGateway
from barthelona.llm.hmem import HMem
from barthelona.llm.markovian import COMPLETE

pytestmark = pytest.mark.skipif(
    shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it"
)

_PROGRAM = """section .data
msg db "{text}", 10
len equ $ - msg
section .text
global _start
_start:
    mov rax, 1
    mov rdi, 1
    mov rsi, msg
    mov rdx, len
    syscall
    mov rax, 60
    xor rdi, rdi
    syscall"""
HELLO = _PROGRAM.format(text="hello")
WRONG = _PROGRAM.format(text="howdy")


def _reply(source: str) -> str:
    return f"```asm\n{source}\n```\n{COMPLETE}"


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
        slug="hello",
        request_original="Print hello.",
        request_lang="en",
        summary_en="Prints hello.",
        target=target,
        requirements=[Requirement(id="R1", text="Writes hello and a newline.", test_ids=["T1"])],
        constraints=["no libc"],
    )


def _cases() -> list[TestCase]:
    return [
        TestCase(
            id="T1",
            kind=TestKind.IO_GOLDEN,
            level=Level.V6,
            inputs={"stdin": ""},
            expect=Expectation(stdout="hello\n", exit_code=0),
            origin=TestOrigin.TEST_AUTHOR,
        )
    ]


async def _generate(replies: list[str], memory: HMem | None = None) -> tuple[FakeGateway, Codegen]:
    gateway = FakeGateway(replies)
    done = await generate_source(
        gateway, _spec(), _cases(), "SYSCALL write=1", memory, None, lambda _r: None, "r1"
    )
    return gateway, done


def test_the_task_names_the_requirements_the_tests_and_the_constraints() -> None:
    text = task_text(_spec(), _cases())
    assert "R1: Writes hello and a newline." in text
    assert "T1: stdin='' -> stdout='hello\\n', exit code 0" in text
    assert "- no libc" in text
    assert "Comment the code" in text
    for clause in (
        "read from fd 0",
        "write to fd 1 or 2",
        "getpid",
        "exit (60)",
        "exit_group (231)",
        "about a million instructions",
        "no terminal, no file",
        "no clock and no graphics",
        "stderr works but is not checked",
    ):
        assert clause in text


def test_check_all_passes_a_program_that_matches_every_test_and_names_the_failing_one() -> None:
    assert check_all(HELLO, _cases(), None).status == "pass"
    wrong = check_all(WRONG, _cases(), None)
    assert wrong.status == "fail"
    assert wrong.errors[0].startswith("test T1: stdout was 'howdy\\n'")


async def test_a_program_that_matches_the_tests_is_accepted_in_one_attempt() -> None:
    gateway, done = await _generate([_reply(HELLO)])
    assert (done.accepted, done.attempts, done.stop) == (True, 1, StopReason.GREEN)
    assert "SYSCALL write=1" in gateway.calls[0][1].messages[1].content


async def test_a_rejected_program_is_repaired_with_the_checker_report() -> None:
    gateway, done = await _generate([_reply(WRONG), _reply(HELLO)])
    assert (done.accepted, done.attempts) == (True, 2)
    repair = gateway.calls[1][1].messages[1].content
    assert "stdout was 'howdy\\n'" in repair
    assert gateway.calls[1][0] == "planner"


async def test_every_attempt_is_handed_out_as_it_is_judged_even_when_rejected() -> None:
    seen: list[tuple[int, str]] = []
    await generate_source(
        FakeGateway([_reply(WRONG), _reply(HELLO)]),
        _spec(),
        _cases(),
        "",
        None,
        None,
        lambda _r: None,
        "r1",
        lambda attempt, source, verdict, chunks: seen.append((attempt, source)),
    )
    assert [attempt for attempt, _ in seen] == [1, 2]
    assert "howdy" in seen[0][1] and "hello" in seen[1][1]


async def test_repairs_are_bounded_and_the_run_stops_as_max_attempts() -> None:
    gateway, done = await _generate([_reply(WRONG)] * 5)
    assert (done.accepted, done.attempts, done.stop) == (False, REPAIRS + 1, StopReason.MAX_ATTEMPTS)
    assert len(gateway.calls) == REPAIRS + 1


async def test_an_answer_without_a_code_block_is_rejected_not_assembled() -> None:
    _, done = await _generate([f"I would write it like this. {COMPLETE}"] * 3)
    assert done.verdict.errors == ("the answer has no code block",)


async def test_an_accepted_run_is_written_to_memory_and_a_rejected_one_is_not() -> None:
    state = "COMPLETED: write. REMAINING: none. DECISIONS: exit through syscall 60 with rdi zero"
    memory = HMem()
    await _generate([f"```asm\n{WRONG}\n```\n{COMPLETE}\n{state}"] * 3, memory)
    assert memory.count() == 0
    await _generate([f"```asm\n{HELLO}\n```\n{COMPLETE}\n{state}"], memory)
    assert memory.count() == 1


def test_the_task_lists_substring_expectations_for_free_text_output() -> None:
    case = _cases()[0].model_copy(update={"expect": Expectation(stdout_contains=["Score: 2"], exit_code=0)})
    assert "T1: stdin='' -> stdout contains ['Score: 2'], exit code 0" in task_text(_spec(), [case])
