"""OpenAIChatBackend against a mocked LM Studio: real SDK, real SSE parsing, no network."""

from __future__ import annotations

import json

import httpx
import pytest
from openai import AsyncOpenAI

from barthelona.llm import ChatMessage, CompletionRequest, ModelCallError, OpenAIChatBackend
from barthelona.llm.catalog import ModelConfig, ModelTarget, ProviderConfig


def _target(*, local: bool = True, structured: str = "json_schema") -> ModelTarget:
    return ModelTarget(
        key="local_main",
        provider_id="lmstudio",
        provider=ProviderConfig(
            kind="openai_chat",
            base_url="http://127.0.0.1:1234/v1",
            local=local,
            structured_output=structured,  # type: ignore[arg-type]
        ),
        model=ModelConfig(provider="lmstudio", model="qwen", price_class="local", context=16384),
    )


def _request(**fields: object) -> CompletionRequest:
    return CompletionRequest(messages=(ChatMessage(role="user", content="hi"),), **fields)  # type: ignore[arg-type]


def _sse(*events: dict[str, object]) -> bytes:
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    return body.encode()


def _chunk(content: str | None, finish: str | None = None) -> dict[str, object]:
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "qwen",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}],
    }


_USAGE: dict[str, object] = {
    "id": "c",
    "object": "chat.completion.chunk",
    "created": 0,
    "model": "qwen",
    "choices": [],
    "usage": {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
        "prompt_tokens_details": {"cached_tokens": 5},
    },
}


def _backend(handler: httpx.MockTransport) -> OpenAIChatBackend:
    def factory(target: ModelTarget) -> AsyncOpenAI:
        client = httpx.AsyncClient(transport=handler)
        return AsyncOpenAI(base_url=target.provider.base_url, api_key="k", max_retries=0, http_client=client)

    return OpenAIChatBackend(env={}, client_factory=factory)


def _ok(seen: list[dict[str, object]]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        events = (_chunk("Hel"), _chunk("lo", "stop"), _USAGE)
        return httpx.Response(200, content=_sse(*events), headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handle)


async def test_streamed_reply_is_assembled_with_usage() -> None:
    seen: list[dict[str, object]] = []
    reply = await _backend(_ok(seen)).complete(_target(), _request(temperature=0.2, seed=7))
    assert (reply.text, reply.stop_reason) == ("Hello", "stop")
    assert (reply.tokens_in, reply.tokens_out, reply.tokens_cached) == (12, 3, 5)
    assert seen[0]["model"] == "qwen"
    assert seen[0]["stream"] is True
    assert seen[0]["temperature"] == 0.2
    assert seen[0]["seed"] == 7
    assert "response_format" not in seen[0]


async def test_schema_becomes_a_strict_json_schema_response_format() -> None:
    seen: list[dict[str, object]] = []
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    await _backend(_ok(seen)).complete(_target(), _request(response_schema=schema))
    assert seen[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "strict": True, "schema": schema},
    }


async def test_schema_without_server_support_is_a_model_error() -> None:
    with pytest.raises(ModelCallError, match="json_schema"):
        await _backend(_ok([])).complete(_target(structured="json_object"), _request(response_schema={}))


async def test_http_errors_become_model_call_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(ModelCallError, match="InternalServerError"):
        await _backend(transport).complete(_target(), _request())


async def test_connection_failures_become_model_call_errors() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelCallError, match="APIConnectionError"):
        await _backend(httpx.MockTransport(refuse)).complete(_target(), _request())


def test_cloud_targets_are_declined_until_their_parameters_are_mapped() -> None:
    backend = OpenAIChatBackend(env={})
    assert backend.unsupported(_target(local=False)) is not None
    assert backend.unsupported(_target()) is None


def _gateway_target() -> ModelTarget:
    return ModelTarget(
        key="meterless_auto",
        provider_id="meterless",
        provider=ProviderConfig(
            kind="openai_chat",
            base_url="http://127.0.0.1:8088/v1",
            plain_chat=True,
            headers={"meterless-app": "barthelona"},
        ),
        model=ModelConfig(provider="meterless", model="meterless/auto", price_class="mid", context=32768),
    )


def test_plain_chat_cloud_gateways_are_accepted() -> None:
    assert OpenAIChatBackend(env={}).unsupported(_gateway_target()) is None


async def test_sampling_parameters_never_reach_a_non_local_gateway() -> None:
    seen: list[dict[str, object]] = []
    await _backend(_ok(seen)).complete(_gateway_target(), _request(temperature=0.2, seed=7))
    assert "temperature" not in seen[0]
    assert "seed" not in seen[0]


async def test_model_extra_body_reaches_the_request() -> None:
    target = _gateway_target()
    thinking_off = {"chat_template_kwargs": {"enable_thinking": False}}
    target = target.model_copy(update={"model": target.model.model_copy(update={"extra_body": thinking_off})})
    seen: list[dict[str, object]] = []
    await _backend(_ok(seen)).complete(target, _request())
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}  # SDK merges extra_body in


def test_provider_headers_are_sent_with_every_request() -> None:
    client = OpenAIChatBackend(env={"METERLESS_RUNTIME_TOKEN": "t"})._default_client(_gateway_target())
    assert client.default_headers["meterless-app"] == "barthelona"


def test_default_client_never_retries_inside_the_sdk() -> None:
    backend = OpenAIChatBackend(env={})
    assert backend._default_client(_target()).max_retries == 0
