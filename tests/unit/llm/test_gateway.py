"""Unit tests for the Gateway router, FakeGateway and think-stripping."""

from __future__ import annotations

import pytest

from barthelona.llm import (
    ChatMessage,
    CompletionRequest,
    FakeGateway,
    Gateway,
    GatewayError,
    ModelCallError,
    RawReply,
    strip_think,
)
from barthelona.llm.catalog import Catalog, ChainEntry, ModelConfig, ModelTarget, ProviderConfig


def _request() -> CompletionRequest:
    return CompletionRequest(messages=(ChatMessage(role="user", content="hi"),))


class _Backend:
    def __init__(self, outcomes: list[RawReply | Exception], unsupported: str | None = None) -> None:
        self.outcomes = outcomes
        self.reason = unsupported
        self.targets: list[str] = []

    def unsupported(self, target: ModelTarget) -> str | None:
        return self.reason

    async def complete(self, target: ModelTarget, request: CompletionRequest) -> RawReply:  # NOSONAR S7503
        self.targets.append(target.key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _catalog(*, cloud_enabled: bool = True, key_env: str | None = None) -> Catalog:
    providers = {
        "cloud": ProviderConfig(kind="anthropic_messages", enabled=cloud_enabled, api_key_env=key_env),
        "lmstudio": ProviderConfig(kind="openai_chat", local=True, base_url="http://127.0.0.1:1234/v1"),
    }
    models = {
        "big": ModelConfig(provider="cloud", model="b", price_class="flagship", context=1000),
        "local_main": ModelConfig(
            provider="lmstudio", model="m", price_class="local", context=1000, strip_think=True
        ),
    }
    chain = [ChainEntry(model="big", params={"effort": "high"}), ChainEntry(model="local_main")]
    return Catalog(providers=providers, models=models, profiles={"p": {"worker": chain}}, default_profile="p")


def _reply(text: str = "ok") -> RawReply:
    return RawReply(text=text, tokens_in=10, tokens_out=4, stop_reason="stop", latency_ms=2000)


def _gateway(cloud: _Backend | None, local: _Backend, **catalog_args: object) -> Gateway:
    backends: dict[str, _Backend] = {"openai_chat": local}
    if cloud is not None:
        backends["anthropic_messages"] = cloud
    return Gateway(_catalog(**catalog_args), backends, env={})  # type: ignore[arg-type]


async def test_first_usable_model_answers_and_the_ledger_row_is_filled() -> None:
    cloud = _Backend([_reply("from cloud")])
    result = await _gateway(cloud, _Backend([])).complete("worker", _request())
    assert (result.text, result.served_by, result.fallbacks) == ("from cloud", "big", ())
    assert result.record.params == {"effort": "high"}
    assert result.record.tok_per_s == pytest.approx(2.0)
    assert result.record.usd is None  # cloud prices arrive with the ledger


async def test_local_call_is_free_and_think_blocks_are_stripped() -> None:
    local = _Backend([_reply("<think>hmm</think>answer")])
    result = await _gateway(None, local, cloud_enabled=False).complete("worker", _request())
    assert (result.text, result.record.usd) == ("answer", 0.0)
    assert result.fallbacks == ("big: disabled",)


async def test_missing_backend_and_missing_key_are_skipped_with_reasons() -> None:
    result = await _gateway(None, _Backend([_reply()]), key_env="NO_SUCH_KEY").complete("worker", _request())
    assert result.fallbacks == ("big: NO_SUCH_KEY is not set",)


async def test_a_backend_that_declines_the_target_is_skipped() -> None:
    cloud = _Backend([], unsupported="not mapped yet")
    result = await _gateway(cloud, _Backend([_reply()])).complete("worker", _request())
    assert result.fallbacks == ("big: not mapped yet",)
    assert cloud.targets == []


async def test_a_failing_model_falls_through_to_the_next() -> None:
    cloud = _Backend([ModelCallError("APIConnectionError: down")])
    result = await _gateway(cloud, _Backend([_reply("local")])).complete("worker", _request())
    assert result.served_by == "local_main"
    assert result.fallbacks[0].startswith("big: APIConnectionError: down after ")


async def test_exhausted_chain_raises_with_every_reason() -> None:
    cloud = _Backend([ModelCallError("boom")])
    local = _Backend([ModelCallError("also boom")])
    with pytest.raises(GatewayError, match=r"boom.*also boom"):
        await _gateway(cloud, local).complete("worker", _request())


async def test_fake_gateway_replays_the_script_and_records_calls() -> None:
    fake = FakeGateway(["one", ModelCallError("down")])
    assert (await fake.complete("worker", _request())).text == "one"
    with pytest.raises(ModelCallError):
        await fake.complete("worker", _request())
    with pytest.raises(GatewayError, match="exhausted"):
        await fake.complete("worker", _request())
    assert [role for role, _ in fake.calls] == ["worker"] * 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<think>a</think>b", "b"),
        ("<think>a\nb</think>\n\nc", "c"),
        ("x<think>cut off", "x"),
        ("  plain  ", "plain"),
        ("<think>a</think>b<think>c</think>d", "bd"),
    ],
)
def test_strip_think(raw: str, expected: str) -> None:
    assert strip_think(raw) == expected
