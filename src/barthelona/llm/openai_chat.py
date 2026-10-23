"""OpenAI Chat Completions backend for LM Studio and Ollama (official ``openai`` SDK, architecture §16.1).

Cloud providers that speak the same protocol (DeepSeek, DashScope) need reasoning-parameter mapping
that is not written yet, so this backend declares them unsupported and the router skips them.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Any

import openai
from openai import AsyncOpenAI

from barthelona.llm.backend import RawReply
from barthelona.llm.catalog import ModelTarget
from barthelona.llm.types import CompletionRequest, ModelCallError

ClientFactory = Callable[[ModelTarget], AsyncOpenAI]
_NO_KEY = "not-needed"  # LM Studio and Ollama ignore the key but the SDK insists on one
_MAX_DETAIL_CHARS = 300


def _describe(exc: openai.OpenAIError) -> str:
    """The error with whatever the server said: status, code, type and a bounded body (never request data)."""
    text = f"{type(exc).__name__}: {exc}"
    extras = [
        f"{name}={value}"
        for name in ("status_code", "code", "type")
        if (value := getattr(exc, name, None)) is not None
    ]
    body = getattr(exc, "body", None)
    if body:
        extras.append(f"body={str(body)[:_MAX_DETAIL_CHARS]}")
    return f"{text} ({', '.join(extras)})" if extras else text


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
            timeout=provider.timeout_s,
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
                raise ModelCallError(f"{target.provider_id} has no json_schema structured output")
            arguments["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": request.response_schema},
            }
        return arguments

    async def complete(self, target: ModelTarget, request: CompletionRequest) -> RawReply:
        arguments = self._arguments(target, request)
        started = time.monotonic()
        parts: list[str] = []
        stop_reason = "unknown"
        usage = None
        try:
            stream = await self._client(target).chat.completions.create(**arguments)
            async for chunk in stream:
                usage = chunk.usage or usage
                for choice in chunk.choices:
                    parts.append(choice.delta.content or "")
                    stop_reason = choice.finish_reason or stop_reason
        except openai.OpenAIError as exc:
            raise ModelCallError(_describe(exc)) from exc
        details = getattr(usage, "prompt_tokens_details", None)
        return RawReply(
            text="".join(parts),
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            tokens_cached=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
            stop_reason=stop_reason,
            latency_ms=round((time.monotonic() - started) * 1000),
        )
