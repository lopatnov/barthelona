"""Chunked long generation after the Meterless Markovian Engine (Apache-2.0, github.com/Meterless/Meterless).

A long job runs as bounded chunks. Each chunk sees the task and a short carryover from the previous
chunk instead of the whole history, so the context of every call stays flat however long the job is.
The model ends a non-final chunk with ``[STATE_CHECKPOINT]`` followed by its state, and the last one with
``[TASK_COMPLETE]``. The loop is bounded by ``max_chunks`` and always ends with a `StopReason` (invariant 6).

Ported from the spec's ARCHITECT mode: the carryover is the model's state block, falling back to the tail
of the chunk. Model-based compression, the RESEARCH mode and the reflection pass are not implemented.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from barthelona.domain.enums import StopReason
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.types import ChatMessage, Completion, CompletionRequest, GatewayError

CHECKPOINT = "[STATE_CHECKPOINT]"
COMPLETE = "[TASK_COMPLETE]"
_CHARS_PER_TOKEN = 4  # rough; only sizes the carryover, real usage comes from the provider
_FRAMING_TOKENS = 400  # the spec's reserve for the system prompt and framing
_MIN_OUTPUT_TOKENS = 1200  # the spec's minimum room for the model's answer
_MIN_STATE_CHARS = 24  # a shorter state block after the marker is not trusted (spec cascade step 1)

CarryoverSource = Literal["state_block", "tail", "none"]

_SYSTEM = (
    "You solve a long task in several bounded steps. You never see earlier steps, only a short state "
    "summary. Do the next part of the work and write only that part.\n"
    f"- If more work remains, end with a line `{CHECKPOINT}` and under it a compact state block with the "
    "labels COMPLETED, REMAINING, DECISIONS and CONTEXT (names and decisions the next step needs).\n"
    f"- When the whole task is finished, end with a line `{COMPLETE}`.\n"
    "Never repeat work that the state summary says is done.\n"
    "Put all code in fenced blocks (three backticks). Text outside the fences is commentary and is dropped."
)
_FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
_SHELL_TAGS = frozenset({"bash", "sh", "shell", "console", "text", "output", "powershell", "cmd", "make"})


def extract_code(text: str) -> str:
    """The source blocks of *text*, joined: fences that are not shell commands or program output."""
    blocks = [
        match.group(2).rstrip("\n")
        for match in _FENCE.finditer(text)
        if match.group(1).strip().lower() not in _SHELL_TAGS
    ]
    return "\n".join(blocks)


@dataclass(frozen=True)
class MarkovianConfig:
    """Defaults and ranges follow the engine's spec: chunk 8000, carryover 800, at most 24 chunks."""

    chunk_tokens: int = 8000
    carryover_tokens: int = 800
    max_chunks: int = 24

    def __post_init__(self) -> None:
        if not 1 <= self.max_chunks <= 32:
            raise ValueError("max_chunks must be between 1 and 32")
        if not 1000 <= self.chunk_tokens <= 128000:
            raise ValueError("chunk_tokens must be between 1000 and 128000")
        if not 128 <= self.carryover_tokens <= 32768:
            raise ValueError("carryover_tokens must be between 128 and 32768")
        floor = _FRAMING_TOKENS + self.carryover_tokens + _MIN_OUTPUT_TOKENS
        if self.chunk_tokens < floor:
            raise ValueError(f"chunk_tokens must be at least {floor} for this carryover_tokens")


@dataclass(frozen=True)
class ChunkStat:
    """One chunk's row for the run report: tokens, latency, who served it and how it ended."""

    index: int
    tokens_in: int
    tokens_out: int
    tokens: int  # this chunk's size in the cost model: provider-measured output tokens, else ceil(chars/4)
    token_source: Literal["measured", "estimated"]
    latency_ms: int
    served_by: str
    marker: Literal["checkpoint", "complete", "none"]
    carryover: CarryoverSource
    fallbacks: tuple[str, ...] = ()  # why earlier chain entries were skipped or failed before this one served


@dataclass(frozen=True)
class MarkovianResult:
    text: str
    stop_reason: StopReason
    chunks: tuple[ChunkStat, ...] = field(default_factory=tuple)
    carryover_tokens: int = 800

    @property
    def tokens_in(self) -> int:
        return sum(chunk.tokens_in for chunk in self.chunks)

    @property
    def tokens_out(self) -> int:
        return sum(chunk.tokens_out for chunk in self.chunks)

    @property
    def status(self) -> str:
        """The engine's run status vocabulary."""
        return {
            StopReason.GREEN: "completed",
            StopReason.MAX_ATTEMPTS: "max-chunks",
        }.get(self.stop_reason, "errored")

    @property
    def standard_cost(self) -> int:
        """Tokens a loop that re-sends its whole history would have spent (spec formula)."""
        total = 0
        history = 0
        for chunk in self.chunks:
            history += chunk.tokens
            total += history
        return total

    @property
    def markovian_cost(self) -> int:
        """Spec formula: n x carryover budget plus the tokens actually used."""
        return len(self.chunks) * self.carryover_tokens + sum(chunk.tokens for chunk in self.chunks)

    @property
    def efficiency_percent(self) -> float:
        saved = max(0, self.standard_cost - self.markovian_cost)
        return saved / self.standard_cost * 100 if self.standard_cost else 0.0

    @property
    def peak_tokens_in(self) -> int:
        """The largest prompt of any chunk: the number that stays flat."""
        return max((chunk.tokens_in for chunk in self.chunks), default=0)


def _split(text: str) -> tuple[str, str, Literal["checkpoint", "complete", "none"]]:
    """The chunk body, the state block after the checkpoint marker, and which marker ended the chunk."""
    if COMPLETE in text:
        return text.split(COMPLETE, 1)[0].rstrip(), "", "complete"
    if CHECKPOINT in text:
        body, state = text.split(CHECKPOINT, 1)
        return body.rstrip(), state.strip(), "checkpoint"
    return text.rstrip(), "", "none"


def _tail_words(body: str, limit_chars: int) -> str:
    """The end of the chunk cut at a word boundary (cascade step 4)."""
    tail = body[-limit_chars:]
    return tail.split(maxsplit=1)[1] if len(body) > limit_chars and " " in tail else tail


def _carryover(body: str, state: str, limit_chars: int) -> tuple[str, CarryoverSource]:
    if len(state) >= _MIN_STATE_CHARS:
        return state[:limit_chars], "state_block"
    if body:
        return _tail_words(body, limit_chars), "tail"
    return "", "none"


def _request(task: str, carryover: str, index: int, config: MarkovianConfig) -> CompletionRequest:
    progress = carryover or "(nothing yet: this is the first step)"
    content = f"Task:\n{task}\n\nStep {index + 1} of at most {config.max_chunks}. State so far:\n{progress}"
    return CompletionRequest(
        messages=(ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=content)),
        max_tokens=config.chunk_tokens - config.carryover_tokens - _FRAMING_TOKENS,
    )


def _stat(index: int, completion: Completion, marker: str, source: CarryoverSource) -> ChunkStat:
    record = completion.record
    measured = record.tokens_out > 0
    return ChunkStat(
        index=index,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        tokens=record.tokens_out if measured else math.ceil(len(completion.text) / _CHARS_PER_TOKEN),
        token_source="measured" if measured else "estimated",
        latency_ms=record.latency_ms,
        served_by=completion.served_by,
        marker=marker,  # type: ignore[arg-type]  # _split returns only the three literals
        carryover=source,
        fallbacks=completion.fallbacks,
    )


async def run_markovian(
    gateway: ModelGateway, role: str, task: str, config: MarkovianConfig | None = None
) -> MarkovianResult:
    """Run *task* as chunks until the model completes it or `max_chunks` is spent."""
    config = config or MarkovianConfig()
    limit_chars = config.carryover_tokens * _CHARS_PER_TOKEN
    bodies: list[str] = []
    stats: list[ChunkStat] = []
    carryover = ""
    for index in range(config.max_chunks):
        try:
            completion = await gateway.complete(role, _request(task, carryover, index, config))
        except GatewayError:
            return MarkovianResult(
                "\n".join(bodies), StopReason.NO_MODEL_AVAILABLE, tuple(stats), config.carryover_tokens
            )
        body, state, marker = _split(completion.text)
        carryover, source = _carryover(body, state, limit_chars) if marker != "complete" else ("", "none")
        bodies.append(body)
        stats.append(_stat(index, completion, marker, source))
        if marker == "complete":
            return MarkovianResult("\n".join(bodies), StopReason.GREEN, tuple(stats), config.carryover_tokens)
    return MarkovianResult("\n".join(bodies), StopReason.MAX_ATTEMPTS, tuple(stats), config.carryover_tokens)
