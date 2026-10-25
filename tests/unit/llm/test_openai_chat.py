"""OpenAIChatBackend against a mocked LM Studio: real SDK, real SSE parsing, no network."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI

from barthelona.llm import ChatMessage, CompletionRequest, FailureKind, ModelCallError, OpenAIChatBackend
from barthelona.llm.catalog import ModelConfig, ModelTarget, ProviderConfig
from barthelona.llm.openai_chat import _describe, _retry_after


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


def _exc_with_header(value: str | None) -> Exception:
    headers = {} if value is None else {"retry-after": value}
    error = Exception("429")
    error.response = SimpleNamespace(headers=headers)  # type: ignore[attr-defined]
    return error


@pytest.mark.parametrize(
    ("header", "expected"),
    [("7", 7.0), ("0.5", 0.5), ("-3", 0.0), (None, None), ("soon", None), ("nan", None)],
)
def test_retry_after_reads_seconds(header: str | None, expected: float | None) -> None:
    assert _retry_after(_exc_with_header(header)) == expected  # type: ignore[arg-type]


def test_retry_after_reads_an_http_date() -> None:
    later = format_datetime(datetime.now(UTC) + timedelta(seconds=40), usegmt=True)
    seconds = _retry_after(_exc_with_header(later))  # type: ignore[arg-type]
    assert seconds is not None
    assert 35 <= seconds <= 40
    past = format_datetime(datetime.now(UTC) - timedelta(seconds=40), usegmt=True)
    assert _retry_after(_exc_with_header(past)) == 0.0  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
async def test_a_separate_reasoning_stream_is_collected_under_either_field_name(field: str) -> None:
    def thinking(request: httpx.Request) -> httpx.Response:
        first = {
            **_chunk(None),
            "choices": [{"index": 0, "delta": {field: "step one, "}, "finish_reason": None}],
        }
        second = {
            **_chunk(None),
            "choices": [{"index": 0, "delta": {field: "step two"}, "finish_reason": None}],
        }
        events = (first, second, _chunk("answer", "stop"))
        return httpx.Response(200, content=_sse(*events), headers={"content-type": "text/event-stream"})

    reply = await _backend(httpx.MockTransport(thinking)).complete(_target(), _request())
    assert (reply.text, reply.reasoning) == ("answer", "step one, step two")


async def test_the_model_the_server_reports_is_kept_as_answered_by() -> None:
    def routed(request: httpx.Request) -> httpx.Response:
        events = [{**_chunk("hi", "stop"), "model": "nvidia/nemotron-3-5-lightning-3"}]
        return httpx.Response(200, content=_sse(*events), headers={"content-type": "text/event-stream"})

    reply = await _backend(httpx.MockTransport(routed)).complete(_target(), _request())
    assert reply.answered_by == "nvidia/nemotron-3-5-lightning-3"


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


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, FailureKind.REFUSAL),
        (401, FailureKind.AUTH),
        (403, FailureKind.AUTH),
        (422, FailureKind.REFUSAL),
        (429, FailureKind.RATE_LIMIT),
        (500, FailureKind.SERVER),
    ],
)
async def test_http_status_decides_the_failure_kind(status: int, kind: FailureKind) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"error": {"message": "no"}}))
    with pytest.raises(ModelCallError) as caught:
        await _backend(transport).complete(_target(), _request())
    assert caught.value.kind is kind


async def test_a_connection_failure_is_transport_and_a_timeout_is_timeout() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def stall(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelCallError) as refused:
        await _backend(httpx.MockTransport(refuse)).complete(_target(), _request())
    with pytest.raises(ModelCallError) as stalled:
        await _backend(httpx.MockTransport(stall)).complete(_target(), _request())
    assert (refused.value.kind, stalled.value.kind) == (FailureKind.TRANSPORT, FailureKind.TIMEOUT)


async def _fail_with(status: int, payload: dict[str, object]) -> ModelCallError:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
    with pytest.raises(ModelCallError) as caught:
        await _backend(transport).complete(_target(), _request())
    return caught.value


def _error(message: str, code: str = "x") -> dict[str, object]:
    return {"message": message, "type": "invalid_request_error", "code": code}


async def test_the_server_message_comes_first_and_its_fix_wins_over_our_hint() -> None:
    payload = {
        "error": _error("lane is loading", "class_not_ready"),
        "meterless": {"fix": ["seat the text lane"]},
    }
    error = await _fail_with(503, payload)
    assert str(error).startswith(
        "APIStatusError: lane is loading | fix: seat the text lane"
    ) or "lane is loading" in str(error)
    assert str(error).index("lane is loading") < str(error).index("fix: seat the text lane")
    assert error.fix == ("seat the text lane",) and error.status == 503 and error.code == "class_not_ready"
    assert "access token" not in str(error)


@pytest.mark.parametrize("status", [401, 403])
async def test_unauthorized_adds_the_token_hint(status: int) -> None:
    error = await _fail_with(status, {"error": _error("bad key", "invalid_api_key")})
    assert "bad key" in str(error) and "METERLESS_RUNTIME_TOKEN" in str(error)
    assert error.kind is FailureKind.AUTH


async def test_repeated_bad_keys_say_do_not_retry() -> None:
    error = await _fail_with(429, {"error": _error("too many bad keys", "auth_rate_limited")})
    assert "do not retry" in str(error)


async def test_a_carrier_refusal_is_never_blamed_on_the_machine_or_given_our_hint() -> None:
    payload = {
        "error": _error("no chat carrier", "class_carrier_unsupported"),
        "meterless": {"chat_carrier": False},
    }
    error = await _fail_with(409, payload)
    text = str(error).lower()
    assert "no chat carrier" in text and "says nothing about this machine" in text
    assert "can't serve" not in text and "hardware" not in text and "start nightshift" not in text
    assert error.chat_carrier is False and error.code == "class_carrier_unsupported"


async def test_a_network_failure_names_the_unreachable_runtime() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ModelCallError) as caught:
        await _backend(httpx.MockTransport(refuse)).complete(_target(), _request())
    assert "isn't reachable at http://127.0.0.1:1234/v1" in str(caught.value)


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


async def test_stream_error_events_keep_the_servers_code_and_body() -> None:
    event = {"error": {"message": "failed after 10.7s", "type": "upstream_error", "code": "empty_response"}}

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse(event), headers={"content-type": "text/event-stream"})

    with pytest.raises(ModelCallError, match="empty_response") as caught:
        await _backend(httpx.MockTransport(handle)).complete(_gateway_target(), _request())
    assert "failed after 10.7s" in str(caught.value)


async def test_model_extra_body_reaches_the_request() -> None:
    target = _gateway_target()
    thinking_off = {"chat_template_kwargs": {"enable_thinking": False}}
    target = target.model_copy(update={"model": target.model.model_copy(update={"extra_body": thinking_off})})
    seen: list[dict[str, object]] = []
    await _backend(_ok(seen)).complete(target, _request())
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}  # SDK merges extra_body in


def test_the_client_waits_long_between_bytes_but_connects_fast() -> None:
    target = _target()
    timeout = OpenAIChatBackend(env={})._default_client(target).timeout

    assert (timeout.read, timeout.write) == (target.provider.timeout_s, 60.0)
    assert timeout.connect == 5.0  # a host that is off fails in seconds, not after the whole read bound


def test_a_timeout_names_the_silent_gap_not_an_unreachable_runtime() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8088/v1/chat/completions")
    text = _describe(APITimeoutError(request=request), "http://127.0.0.1:8088/v1")

    assert "no bytes arrived" in text
    assert "isn't reachable" not in text and "start Nightshift" not in text


def test_provider_headers_are_sent_with_every_request() -> None:
    client = OpenAIChatBackend(env={"METERLESS_RUNTIME_TOKEN": "t"})._default_client(_gateway_target())
    assert client.default_headers["meterless-app"] == "barthelona"


def test_default_client_never_retries_inside_the_sdk() -> None:
    backend = OpenAIChatBackend(env={})
    assert backend._default_client(_target()).max_retries == 0
