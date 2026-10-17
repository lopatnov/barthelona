"""Run one bench task under one arm: first attempt, then up to N oracle-feedback fix attempts.

The loop is bounded by the arm's attempt and token limits and every stop carries a `StopReason`
(invariant 6). The model's files are written to a scratch workspace, restricted to the task's one
source file; the ladder stages `gen/` itself, so a model cannot tamper with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import Field

from barthelona.bench.prompts import PromptSet, render_feedback, render_first_prompt, render_fix_prompt
from barthelona.bench.task import BenchTask
from barthelona.domain._base import DomainModel
from barthelona.domain.enums import StopReason
from barthelona.domain.verification import LevelResult
from barthelona.llm import ChatMessage, CompletionRequest, GatewayError, ModelGateway
from barthelona.prompting import EnvelopeError, parse_files
from barthelona.verification import dod_satisfied


class Verifier(Protocol):
    """Runs the oracle ladder on staged source files."""

    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]: ...


@dataclass(frozen=True)
class Arm:
    name: str
    max_fix_iterations: int  # 0 is the bare single prompt
    max_total_tokens: int = 60_000  # input + output over all attempts of one task


@dataclass(frozen=True)
class RunSettings:
    role: str = "worker"
    temperature: float = 0.2
    max_tokens: int = 4096


class AttemptResult(DomainModel):
    number: int
    envelope_errors: tuple[str, ...] = ()
    levels: dict[str, str] = Field(default_factory=dict)  # level -> status
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    tok_per_s: float | None = None
    served_by: str = ""
    passed: bool = False


class TaskResult(DomainModel):
    task_id: str
    arm: str
    seed: int
    stop_reason: StopReason
    attempts: tuple[AttemptResult, ...]

    @property
    def passed(self) -> bool:
        return self.stop_reason == StopReason.GREEN

    @property
    def first_try(self) -> bool:
        return bool(self.attempts) and self.attempts[0].passed


@dataclass(frozen=True)
class TaskRun:
    """Everything one task execution shares between its attempts."""

    task: BenchTask
    seed: int
    gateway: ModelGateway
    verifier: Verifier
    prompts: PromptSet
    source_name: str
    work_root: Path
    settings: RunSettings

    @property
    def run_id(self) -> str:
        return f"bench-{self.task.id}-{self.seed}"


@dataclass(frozen=True)
class _Turn:
    """The previous model reply and the oracle feedback on it (both None on the first attempt)."""

    reply: str
    fix_prompt: str


def _messages(first_prompt: str, previous: _Turn | None) -> tuple[ChatMessage, ...]:
    messages = [ChatMessage(role="user", content=first_prompt)]
    if previous is not None:
        messages.append(ChatMessage(role="assistant", content=previous.reply))
        messages.append(ChatMessage(role="user", content=previous.fix_prompt))
    return tuple(messages)


def _write(workspace: Path, name: str, content: str) -> list[Path]:
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / name
    path.write_text(content, encoding="utf-8", newline="\n")
    return [path]


async def _attempt(
    run: TaskRun, arm: Arm, number: int, first_prompt: str, previous: _Turn | None
) -> tuple[AttemptResult, _Turn]:
    """One model call and, when its reply parses, one ladder run. Raises `GatewayError`."""
    request = CompletionRequest(
        messages=_messages(first_prompt, previous),
        max_tokens=run.settings.max_tokens,
        temperature=run.settings.temperature,
        seed=run.seed,
    )
    completion = await run.gateway.complete(run.settings.role, request)
    record = completion.record
    attempt = AttemptResult(
        number=number,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        latency_ms=record.latency_ms,
        tok_per_s=record.tok_per_s,
        served_by=completion.served_by,
    )
    try:
        files = parse_files(completion.text, write_scope=[run.source_name])
    except EnvelopeError as exc:
        feedback = "Your reply was not accepted: " + "; ".join(exc.errors)
        attempt = attempt.model_copy(update={"envelope_errors": exc.errors})
    else:
        workspace = run.work_root / f"{run.run_id}-{arm.name}" / str(number)
        sources = _write(workspace, run.source_name, files[0].content)
        results = await run.verifier.verify(run.task, sources, f"{run.run_id}-{arm.name}", number)
        passed = dod_satisfied(run.task.required_levels, results)
        levels = {str(r.level): r.status for r in results}
        attempt = attempt.model_copy(update={"levels": levels, "passed": passed})
        feedback = render_feedback(results)
    fix_prompt = render_fix_prompt(run.prompts, run.task, run.source_name, feedback)
    return attempt, _Turn(completion.text, fix_prompt)


async def run_task(run: TaskRun, arm: Arm) -> TaskResult:
    first_prompt = render_first_prompt(run.prompts, run.task, run.source_name)
    attempts: list[AttemptResult] = []
    previous: _Turn | None = None
    spent = 0
    stop = StopReason.MAX_ATTEMPTS
    for number in range(arm.max_fix_iterations + 1):
        if spent >= arm.max_total_tokens:
            stop = StopReason.BUDGET_TOKENS
            break
        try:
            attempt, previous = await _attempt(run, arm, number, first_prompt, previous)
        except GatewayError:
            stop = StopReason.NO_MODEL_AVAILABLE
            break
        attempts.append(attempt)
        spent += attempt.tokens_in + attempt.tokens_out
        if attempt.passed:
            stop = StopReason.GREEN
            break
    return TaskResult(
        task_id=run.task.id, arm=arm.name, seed=run.seed, stop_reason=stop, attempts=tuple(attempts)
    )
