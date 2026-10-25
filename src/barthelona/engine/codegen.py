"""`codegen` for a single-module create run: the chunk loop writes the source, the oracles decide.

Reduced form of the sprint loop (docs/architecture.md §6.2) for the first end-to-end slice: no contracts, no
sprint graph. The Markovian chunk loop (with Zetaris facts and H-MEM recall in every chunk) writes one NASM
source file from the approved spec. NASM assembles it and the Unicorn emulator runs every golden test; the
model never decides (invariant 1). A rejected attempt goes back with the checker's report, at most `REPAIRS`
times (invariant 6). Only an accepted source is written to H-MEM.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass

from barthelona.domain import LLMCallRecord, ProjectSpec, StopReason, TestCase
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.guard import wrap_untrusted
from barthelona.llm.hmem import RECALL_TOP_N, HMem, chunk_recall, facts_from_state
from barthelona.llm.markovian import (
    MarkovianConfig,
    MarkovianResult,
    extract_code,
    run_markovian,
    source_blocks,
)
from barthelona.llm.types import Completion, CompletionRequest
from barthelona.verification.asm_gate import AssembleResult, assemble_best
from barthelona.verification.behavior_gate import Expectation, check_behavior
from barthelona.world_model import WorldModel, format_entities

# Each repair sees the checker report (assembler errors, end of the wrong output); a quiz needed over 2.
REPAIRS = 4
WRITE_ROLE = "worker"
REPAIR_ROLE = "planner"
DOMAIN = "assembly"
# A reasoning model spends part of a chunk on thinking; 2000 cut a 12-question quiz off mid-instruction.
CHUNKS = MarkovianConfig(chunk_tokens=6000, carryover_tokens=128, max_chunks=8)

OnCall = Callable[[LLMCallRecord], None]
# (attempt number from 1, its source, the oracle's verdict, the chunks used so far), even when rejected.
OnAttempt = Callable[[int, str, AssembleResult, int], None]


@dataclass(frozen=True)
class Codegen:
    """The last attempt: its source, the oracle's verdict on it and how much work it took."""

    source: str
    verdict: AssembleResult
    attempts: int
    chunks: int
    stop: StopReason

    @property
    def accepted(self) -> bool:
        return self.verdict.status == "pass"


class _Recording:
    """A gateway that puts every call into the ledger, so chunk calls are counted like any other."""

    def __init__(self, inner: ModelGateway, on_call: OnCall) -> None:
        self._inner = inner
        self._on_call = on_call

    async def complete(
        self, role: str, request: CompletionRequest, avoid: Collection[str] = ()
    ) -> Completion:
        completion = await self._inner.complete(role, request, avoid)
        self._on_call(completion.record)
        return completion


def _example(case: TestCase) -> str:
    stdin = case.inputs.get("stdin", "")
    wanted = []
    if case.expect.stdout is not None:
        wanted.append(f"stdout={case.expect.stdout!r}")
    if case.expect.stdout_contains:
        wanted.append(f"stdout contains {case.expect.stdout_contains!r}")
    output = " and ".join(wanted) or "any stdout"
    return f"{case.id}: stdin={stdin!r} -> {output}, exit code {case.expect.exit_code or 0}"


def task_text(spec: ProjectSpec, cases: list[TestCase]) -> str:
    """The prompt for the chunk loop: what the program does and the exact behavior the emulator will check."""
    requirements = "\n".join(f"{r.id}: {r.text}" for r in spec.requirements)
    examples = "\n".join(_example(case) for case in cases)
    constraints = "".join(f"\n- {line}" for line in spec.constraints)
    return (
        "Write a NASM program for Linux x86-64 (elf64, syscalls only, no libc, global _start, finish with "
        "the exit syscall). Return one complete source file in a single code block. "
        "Comment the code with ';' comments: a header saying what the program does, one line for every "
        "section and label, and a note on each syscall and any instruction whose purpose is not obvious.\n"
        f"Program: {spec.summary_en}\nRequirements:\n{requirements}\n"
        "Environment: the emulator allows only these syscalls: read from fd 0, write to fd 1 or 2, getpid, "
        "exit (60) and exit_group (231). Any other syscall (mmap, brk, nanosleep, ioctl, open, ...) fails "
        "the test, and a test is cut off after about a million instructions. There is no terminal, no file, "
        "no clock and no graphics: the program reads stdin and writes stdout "
        "(stderr works but is not checked).\n"
        "Acceptance tests (run in an emulator; the exit code must match, stdout must match exactly "
        f"unless a test says it contains texts, which only have to appear in it):\n{examples}"
        + (f"\nConstraints:{constraints}" if constraints else "")
    )


def check_all(source: str, cases: list[TestCase], nasm: str | None) -> AssembleResult:
    """``pass`` when *source* assembles and every golden test matches in the emulator; first failure wins."""
    verdict = AssembleResult("fail", ("no test cases to run",))
    for case in cases:
        stdout = case.expect.stdout
        expect = Expectation(
            stdout.encode("utf-8") if stdout is not None else None,
            case.expect.exit_code or 0,
            str(case.inputs.get("stdin", "")).encode("utf-8"),
            tuple(text.encode("utf-8") for text in case.expect.stdout_contains),
        )
        verdict = check_behavior(source, expect, nasm)
        if verdict.status != "pass":
            return AssembleResult(verdict.status, tuple(f"test {case.id}: {e}" for e in verdict.errors))
    return verdict


def _judge(result: MarkovianResult, cases: list[TestCase], nasm: str | None) -> tuple[str, AssembleResult]:
    code = extract_code(result.text)
    if not code.strip():
        return "", AssembleResult("fail", ("the answer has no code block",))
    chosen, verdict = assemble_best(code, source_blocks(result.text), nasm)
    if verdict.status == "pass":
        verdict = check_all(chosen, cases, nasm)
    return chosen, verdict


def _repair_prompt(task: str, source: str, verdict: AssembleResult) -> str:
    errors = wrap_untrusted("\n".join(verdict.errors), "oracle")
    return (
        f"{task}\n\nYour previous attempt was rejected when it was assembled and run. The checker reported:\n"
        f"{errors}\n\nPrevious source:\n```asm\n{source}\n```\n"
        "Write the complete corrected program exactly once, in a single fenced block."
    )


def _stop_for(verdict: AssembleResult, result: MarkovianResult) -> StopReason:
    if verdict.status == "pass":
        return StopReason.GREEN
    if verdict.status == "unavailable":
        return StopReason.INFRA_ERROR  # a gate that cannot run does not pass
    if result.stop_reason is StopReason.NO_MODEL_AVAILABLE and not result.text:
        return StopReason.NO_MODEL_AVAILABLE
    return StopReason.MAX_ATTEMPTS


async def generate_source(
    gateway: ModelGateway,
    spec: ProjectSpec,
    cases: list[TestCase],
    facts: str,
    memory: HMem | None,
    nasm: str | None,
    on_call: OnCall,
    run_id: str,
    on_attempt: OnAttempt | None = None,
    world: WorldModel | None = None,
) -> Codegen:
    """Write the source, let the oracles judge it, repair up to `REPAIRS` times, remember it if accepted."""
    recording = _Recording(gateway, on_call)
    task = task_text(spec, cases)
    recalled = memory.query(task, domain=DOMAIN, top_n=RECALL_TOP_N).context if memory else ""
    recall = chunk_recall(memory, task, DOMAIN)
    prompt, chunks = task, 0
    for attempt in range(REPAIRS + 1):
        role = REPAIR_ROLE if attempt else WRITE_ROLE
        world_context = world_context_block(world, spec.slug, run_id) if world is not None else ""
        context = "\n\n".join(filter(None, [facts, world_context, recalled]))
        result = await run_markovian(recording, role, prompt, CHUNKS, context, recall)
        chunks += len(result.chunks)
        source, verdict = await asyncio.to_thread(_judge, result, cases, nasm)  # subprocess and emulator
        if on_attempt is not None and source.strip():
            on_attempt(attempt + 1, source, verdict, chunks)  # a draft on disk, and its verdict in the world
        stop = _stop_for(verdict, result)
        if verdict.status != "fail" or stop is StopReason.NO_MODEL_AVAILABLE:
            break
        prompt = _repair_prompt(task, source, verdict)
    if memory is not None and verdict.status == "pass":
        lessons = [fact for chunk in result.chunks for fact in facts_from_state(chunk.state)]
        memory.ingest(lessons, source=f"run:{run_id}:{int(time.time())}", domain=DOMAIN)
    return Codegen(source, verdict, attempt + 1, chunks, stop)


def world_context_block(world: WorldModel, slug: str, run_id: str) -> str:
    """What earlier runs of this task produced, as an untrusted block next to Zetaris facts and H-MEM."""
    prior = [entity for entity in world.entities(slug=slug) if entity.run_id != run_id]
    if not prior:
        return ""
    return "[WORLD MODEL] what earlier runs of this task produced\n" + wrap_untrusted(
        format_entities(prior), "world-model"
    )
