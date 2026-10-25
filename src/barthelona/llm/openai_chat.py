"""OpenAI Chat Completions backend for LM Studio and Ollama (official ``openai`` SDK, architecture §16.1).

Cloud providers that speak the same protocol (DeepSeek, DashScope) need reasoning-parameter mapping
that is not written yet, so this backend declares them unsupported and the router skips them.
"""

from __future__ import annotations

import email.utils
import math
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import openai
from openai import AsyncOpenAI

from barthelona.llm.backend import RawReply
from barthelona.llm.catalog import ModelTarget
from barthelona.llm.types import CompletionRequest, FailureKind, ModelCallError

ClientFactory = Callable[[ModelTarget], AsyncOpenAI]
_NO_KEY = "not-needed"  # LM Studio and Ollama ignore the key but the SDK insists on one
_MAX_DETAIL_CHARS = 300
# The read timeout is the silent gap between streamed bytes, not the length of the call, so it is generous
# (a reasoning lane may think for minutes while still streaming). A dead host must fail fast instead.
_CONNECT_TIMEOUT_S = 5.0
_WRITE_TIMEOUT_S = 60.0


def _meterless_block(exc: openai.OpenAIError) -> dict[str, Any]:
    """The runtime's ``meterless`` block (fix[], class, chat_carrier, routes) beside ``error`` in the body."""
    response = getattr(exc, "response", None)
    try:
        block = response.json().get("meterless") if response is not None else None
    except (ValueError, AttributeError):
        return {}
    return block if isinstance(block, dict) else {}


def _own_hint(exc: openai.OpenAIError, base_url: str | None) -> str:
    """Our hint, used only when the server sent no fix and the route did not refuse the class."""
    if isinstance(exc, openai.APITimeoutError):  # a subclass of APIConnectionError, so it is asked first
        return (
            f"no bytes arrived from {base_url or 'the provider'} for its whole read timeout: the lane may be "
            "loading a model or its upstream may be busy; it is retried, and timeout_s raises the bound"
        )
    if isinstance(exc, openai.APIConnectionError):
        return (
            f"the runtime isn't reachable at {base_url or 'its base URL'}: start Nightshift and check the URL"
        )
    status = getattr(exc, "status_code", None)
    if status == 429 and getattr(exc, "code", None) == "auth_rate_limited":
        return "repeated bad keys: fix METERLESS_RUNTIME_TOKEN, do not retry"
    if status in (401, 403):
        return "paste the runtime's access token from the Nightshift Console into METERLESS_RUNTIME_TOKEN"
    return ""


def _is_carrier_refusal(exc: openai.OpenAIError, block: dict[str, Any]) -> bool:
    return getattr(exc, "code", None) == "class_carrier_unsupported" or block.get("chat_carrier") is False


def _describe(exc: openai.OpenAIError, base_url: str | None = None) -> str:
    """The server's message first, its fix[] next; our hint only without a fix or a carrier refusal."""
    block = _meterless_block(exc)
    body = getattr(exc, "body", None)
    message = body.get("message") if isinstance(body, dict) else None
    parts = [f"{type(exc).__name__}: {message or exc}"]
    fixes = [str(item) for item in block.get("fix") or []]
    if fixes:
        parts.append("fix: " + "; ".join(fixes))
    elif _is_carrier_refusal(exc, block):
        parts.append("this route cannot carry the class; that says nothing about this machine")
    elif hint := _own_hint(exc, base_url):
        parts.append(hint)
    extras = [
        f"{name}={value}"
        for name in ("status_code", "code", "type")
        if (value := getattr(exc, name, None)) is not None
    ]
    if body and not message:
        extras.append(f"body={str(body)[:_MAX_DETAIL_CHARS]}")
    return " | ".join(parts) + (f" ({', '.join(extras)})" if extras else "")


def _retry_after(exc: openai.OpenAIError) -> float | None:
    """The ``Retry-After`` header in seconds, from its number or HTTP-date form, if the provider sent one."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        value = response.headers["retry-after"]
    except (KeyError, AttributeError):
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (email.utils.parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _call_error(exc: openai.OpenAIError, base_url: str | None) -> ModelCallError:
    block = _meterless_block(exc)
    return ModelCallError(
        _describe(exc, base_url),
        _kind(exc),
        status=getattr(exc, "status_code", None),
        code=getattr(exc, "code", None),
        fix=tuple(str(item) for item in block.get("fix") or []),
        chat_carrier=block.get("chat_carrier"),
        retry_after=_retry_after(exc),
    )


def _kind(exc: openai.OpenAIError) -> FailureKind:
    if isinstance(exc, openai.APITimeoutError):
        return FailureKind.TIMEOUT
    if isinstance(exc, openai.APIConnectionError):
        return FailureKind.TRANSPORT
    if isinstance(exc, openai.RateLimitError):
        return FailureKind.RATE_LIMIT
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return FailureKind.AUTH
    if isinstance(exc, openai.BadRequestError | openai.UnprocessableEntityError):
        return FailureKind.REFUSAL
    return FailureKind.SERVER  # 5xx, other statuses and error events inside the stream


class OpenAIChatBackend:
    def __init__(
        self, env: Mapping[str, str] | None = None, client_factory: ClientFactory | None = None
    ) -> None:
        self._env = os.environ if env is None else env
        self._client_factory = client_factory or self._default_client
        self._clients: dict[str, AsyncOpenAI] = {}

    def _default_client(self, target: ModelTarget) -> AsyncOpenAI:
        provider = target.provider
        key = self._env.get(provider.api_key_env or "") or _NO_KEY
        # SDK retries off: attempts are counted by the gateway, not multiplied by the SDK.
        return AsyncOpenAI(
            base_url=provider.base_url,
            api_key=key,
            max_retries=0,
            # The SDK normalizes a legacy httpx.Timeout at runtime; its annotation only names the httpx2
            # type it bundles, so the mismatch is in the signature, not in the value.
            timeout=httpx.Timeout(  # type: ignore[arg-type]
                connect=_CONNECT_TIMEOUT_S,
                read=provider.timeout_s,
                write=_WRITE_TIMEOUT_S,
                pool=provider.timeout_s,
            ),
            default_headers=provider.headers or None,
        )

    def _client(self, target: ModelTarget) -> AsyncOpenAI:
        if target.provider_id not in self._clients:
            self._clients[target.provider_id] = self._client_factory(target)
        return self._clients[target.provider_id]

    def unsupported(self, target: ModelTarget) -> str | None:
        if not target.provider.local and not target.provider.plain_chat:
            return "cloud reasoning parameters are not mapped yet"
        if not target.provider.base_url:
            return "no base_url"
        return None

    def _arguments(self, target: ModelTarget, request: CompletionRequest) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "model": target.model.model,
            "messages": [message.model_dump() for message in request.messages],
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if target.model.extra_body:
            arguments["extra_body"] = target.model.extra_body
        if request.temperature is not None and target.provider.local:
            arguments["temperature"] = request.temperature  # sampling parameters reach local models only
        if request.seed is not None and target.provider.local:
            arguments["seed"] = request.seed
        if request.response_schema is not None:
            if target.provider.structured_output != "json_schema":
                raise ModelCallError(
                    f"{target.provider_id} has no json_schema structured output", FailureKind.REFUSAL
                )
            arguments["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": request.response_schema},
            }
        return arguments

    async def complete(self, target: ModelTarget, request: CompletionRequest) -> RawReply:
        arguments = self._arguments(target, request)
        started = time.monotonic()
        parts: list[str] = []
        thoughts: list[str] = []
        stop_reason = "unknown"
        usage = None
        answered_by = ""
        try:
            stream = await self._client(target).chat.completions.create(**arguments)
            async for chunk in stream:
                usage = chunk.usage or usage
                answered_by = chunk.model or answered_by
                for choice in chunk.choices:
                    parts.append(choice.delta.content or "")
                    # Servers that separate reasoning send it as an extra delta field, under either name.
                    thoughts.append(
                        getattr(choice.delta, "reasoning_content", None)
                        or getattr(choice.delta, "reasoning", None)
                        or ""
                    )
                    stop_reason = choice.finish_reason or stop_reason
        except openai.OpenAIError as exc:
            raise _call_error(exc, target.provider.base_url) from exc
        details = getattr(usage, "prompt_tokens_details", None)
        return RawReply(
            text="".join(parts),
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            tokens_cached=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
            stop_reason=stop_reason,
            latency_ms=round((time.monotonic() - started) * 1000),
            answered_by=answered_by,
            reasoning="".join(thoughts),
        )
