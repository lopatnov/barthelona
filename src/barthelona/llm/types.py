"""Request and response models of the model gateway (docs/architecture.md §16.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from barthelona.domain._base import DomainModel
from barthelona.domain.run import LLMCallRecord


class ChatMessage(DomainModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompletionRequest(DomainModel):
    """One chat call. Sampling parameters reach local models only (`.claude/rules/llm-gateway.md`)."""

    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    max_tokens: int = Field(default=2048, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    seed: int | None = None  # reproducible sampling on local servers; the bench varies it per run
    response_schema: dict[str, Any] | None = None  # JSON schema for small structured artifacts only


class Completion(DomainModel):
    """A finished call: the text without `<think>` blocks, the ledger row and how the chain got here."""

    text: str
    record: LLMCallRecord
    served_by: str  # catalog key of the model that answered
    fallbacks: tuple[str, ...] = ()  # one reason per chain entry that was skipped or failed first
    answered_by: str = ""  # the model id the provider reported, e.g. the lane a router picked


class GatewayError(RuntimeError):
    """A call could not be completed. `ModelCallError` is raised by a backend, this by the whole chain."""


class FailureKind(StrEnum):
    """Why one model failed, so a fall-through to the next chain entry is never reported as a bare error."""

    TRANSPORT = "transport"  # connection refused/reset, DNS, stream cut
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"  # 401/403: key missing, rejected or without access
    REFUSAL = "refusal"  # 400/422: the provider rejected this request (policy, content filter, bad parameter)
    SERVER = "server"  # 5xx or an error event inside the stream
    BAD_REPLY = "bad_reply"  # the reply arrived but is unusable


class ModelCallError(GatewayError):
    """One model failed (connection, timeout, bad response); the router tries the next chain entry."""

    def __init__(
        self,
        message: str,
        kind: FailureKind = FailureKind.TRANSPORT,
        *,
        status: int | None = None,
        code: str | None = None,
        fix: tuple[str, ...] = (),
        chat_carrier: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status  # what the server sent, kept on the error object for callers
        self.code = code
        self.fix = fix
        self.chat_carrier = chat_carrier
