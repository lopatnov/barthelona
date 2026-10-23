"""The backend protocol and the completion builder shared by every backend and the fake gateway."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import orjson

from barthelona.domain.run import LLMCallRecord
from barthelona.llm.catalog import ModelTarget
from barthelona.llm.thinking import strip_think
from barthelona.llm.types import Completion, CompletionRequest


@dataclass(frozen=True)
class RawReply:
    """What a backend got from the provider, before think-stripping and ledger bookkeeping."""

    text: str
    tokens_in: int
    tokens_out: int
    stop_reason: str
    latency_ms: int
    tokens_cached: int = 0
    answered_by: str = ""  # the model id the server says answered (a router may differ from the requested id)


class Backend(Protocol):
    """Talks to one provider kind with its official SDK."""

    def unsupported(self, target: ModelTarget) -> str | None:
        """Why this backend cannot serve *target* (None when it can); the router skips it."""
        ...

    async def complete(self, target: ModelTarget, request: CompletionRequest) -> RawReply:
        """One call; raises `ModelCallError` when the model fails."""
        ...


def prompt_hash(target: ModelTarget, request: CompletionRequest) -> str:
    """sha256 over messages, schema and per-role parameters; the ledger never stores prompt text."""
    payload = {"request": request.model_dump(mode="json"), "params": target.params}
    return hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def build_completion(
    target: ModelTarget, request: CompletionRequest, reply: RawReply, fallbacks: tuple[str, ...] = ()
) -> Completion:
    seconds = reply.latency_ms / 1000
    record = LLMCallRecord(
        provider=target.provider_id,
        model=target.model.model,
        params=dict(target.params),
        prompt_hash=prompt_hash(target, request),
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
        tokens_cached=reply.tokens_cached,
        latency_ms=reply.latency_ms,
        tok_per_s=reply.tokens_out / seconds if seconds > 0 and reply.tokens_out else None,
        schema_valid=None,
        usd=0.0 if target.provider.local else None,  # cloud prices arrive with the ledger
        stop_reason=reply.stop_reason,
    )
    text = strip_think(reply.text) if target.model.strip_think else reply.text.strip()
    return Completion(
        text=text,
        record=record,
        served_by=target.key,
        fallbacks=fallbacks,
        answered_by=reply.answered_by,
    )
