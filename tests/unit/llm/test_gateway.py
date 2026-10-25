"""Unit tests for the Gateway router, FakeGateway and think-stripping."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from barthelona.llm import (
    ChatMessage,
    CompletionRequest,
    FailureKind,
    FakeGateway,
    Gateway,
    GatewayError,
    ModelCallError,
    RawReply,
    strip_think,
)
from barthelona.llm.catalog import (
    Catalog,
    ChainEntry,
    ModelConfig,
    ModelTarget,
    ProviderConfig,
    ResilienceConfig,
    RetryConfig,
)


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


def _policy(retry: RetryConfig) -> Catalog:
    """The test catalog with a retry policy of its own, as `resilience.retry` would set it."""
    return _catalog().model_copy(update={"resilience": ResilienceConfig(retry=retry)})


def _gateway(
    cloud: _Backend | None,
    local: _Backend,
    retry_delays: tuple[float, ...] = (),
    sleeps: list[float] | None = None,
    progress: Callable[[str], None] | None = None,
    **catalog_args: object,
) -> Gateway:
    backends: dict[str, _Backend] = {"openai_chat": local}
    if cloud is not None:
        backends["anthropic_messages"] = cloud

    async def sleep(seconds: float) -> None:  # NOSONAR S7503
        if sleeps is not None:
            sleeps.append(seconds)

    return Gateway(
        _catalog(**catalog_args),
        backends,  # type: ignore[arg-type]
        env={},
        retry_delays=retry_delays,
        sleep=sleep,
        progress=progress,
        jitter=lambda cap: cap,  # the upper end of the jitter range, so the delays are predictable
    )


async def test_first_usable_model_answers_and_the_ledger_row_is_filled() -> None:
    cloud = _Backend([_reply("from cloud")])
    result = await _gateway(cloud, _Backend([])).complete("worker", _request())
    assert (result.text, result.served_by, result.fallbacks) == ("from cloud", "big", ())
    assert result.record.params == {"effort": "high"}
    assert result.record.tok_per_s == pytest.approx(2.0)
    assert result.record.usd is None  # cloud prices arrive with the ledger


async def test_a_model_the_caller_could_not_use_is_skipped_for_the_next_one() -> None:
    cloud, local = _Backend([_reply("from cloud")]), _Backend([_reply("from local")])
    said: list[str] = []
    result = await _gateway(cloud, local, progress=said.append).complete("worker", _request(), avoid={"big"})
    assert (result.text, result.served_by) == ("from local", "local_main")
    assert result.fallbacks == ("big: skipped, its last reply was unusable",)
    assert cloud.targets == []  # a model the caller cannot use is not asked again
    assert "FAILED big skipped: its last reply was unusable" in said


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


async def test_the_fall_through_reason_carries_the_failure_kind() -> None:
    cloud = _Backend([ModelCallError("BadRequestError: policy", FailureKind.REFUSAL)])
    result = await _gateway(cloud, _Backend([_reply("local")])).complete("worker", _request())
    assert result.fallbacks[0].endswith("[refusal]")


async def test_exhausted_chain_raises_with_every_reason() -> None:
    cloud = _Backend([ModelCallError("boom")])
    local = _Backend([ModelCallError("also boom")])
    with pytest.raises(GatewayError, match=r"boom.*also boom"):
        await _gateway(cloud, local).complete("worker", _request())


async def test_a_timeout_is_repeated_on_the_same_model_before_falling_through() -> None:
    cloud = _Backend(
        [ModelCallError("APITimeoutError: Request timed out", FailureKind.TIMEOUT), _reply("from cloud")]
    )
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([]), retry_delays=(0.5,), sleeps=sleeps)

    result = await gateway.complete("worker", _request())

    assert (result.served_by, cloud.targets, sleeps) == ("big", ["big", "big"], [0.5])
    assert result.fallbacks[0].startswith("big: retry in 0.5s: APITimeoutError")


async def test_a_second_timeout_is_not_repeated_even_when_attempts_remain() -> None:
    cloud = _Backend([ModelCallError("APITimeoutError: stalled", FailureKind.TIMEOUT) for _ in range(3)])
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([_reply("local")]), retry_delays=(0.5, 1.5), sleeps=sleeps)

    result = await gateway.complete("worker", _request())

    assert (result.served_by, cloud.targets, sleeps) == ("local_main", ["big", "big"], [0.5])
    assert len(result.fallbacks) == 2  # the repeat and the second stall, which moves the chain on


async def test_the_retry_policy_and_its_jitter_come_from_the_catalog() -> None:
    cloud = _Backend([ModelCallError("busy", FailureKind.SERVER) for _ in range(3)])
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:  # NOSONAR S7503
        sleeps.append(seconds)

    gateway = Gateway(
        _policy(RetryConfig(max_attempts=2, base_delay_s=0.25, max_delay_s=1.0, jitter="none")),
        {"anthropic_messages": cloud, "openai_chat": _Backend([_reply("local")])},  # type: ignore[arg-type]
        env={},
        sleep=sleep,
    )

    result = await gateway.complete("worker", _request())

    assert (result.served_by, cloud.targets, sleeps) == ("local_main", ["big", "big"], [0.25])


async def test_retry_after_can_be_ignored_by_the_catalog() -> None:
    cloud = _Backend([ModelCallError("429", FailureKind.RATE_LIMIT, retry_after=4.0), _reply("from cloud")])
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:  # NOSONAR S7503
        sleeps.append(seconds)

    gateway = Gateway(
        _policy(RetryConfig(max_attempts=2, base_delay_s=0.5, jitter="none", honor_retry_after=False)),
        {"anthropic_messages": cloud, "openai_chat": _Backend([])},  # type: ignore[arg-type]
        env={},
        sleep=sleep,
    )

    result = await gateway.complete("worker", _request())

    assert (result.served_by, sleeps) == ("big", [0.5])


async def test_a_transient_failure_is_repeated_on_the_same_model_before_falling_through() -> None:
    cloud = _Backend(
        [ModelCallError("APIError: 404 provider_error", FailureKind.SERVER), _reply("from cloud")]
    )
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([]), retry_delays=(0.5, 1.5), sleeps=sleeps)
    result = await gateway.complete("worker", _request())
    assert (result.served_by, result.text, cloud.targets) == ("big", "from cloud", ["big", "big"])
    assert sleeps == [0.5]
    assert result.fallbacks[0].startswith("big: retry in 0.5s: APIError: 404 provider_error after ")
    assert len(result.fallbacks) == 1


async def test_repeats_are_bounded_then_the_chain_moves_on() -> None:
    errors = [ModelCallError("down", FailureKind.SERVER) for _ in range(3)]
    cloud = _Backend(list(errors))
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([_reply("local")]), retry_delays=(0.5, 1.5), sleeps=sleeps)
    result = await gateway.complete("worker", _request())
    assert (result.served_by, cloud.targets, sleeps) == ("local_main", ["big"] * 3, [0.5, 1.5])
    assert len(result.fallbacks) == 3  # two repeats and the final failure


async def test_retry_after_is_the_minimum_wait_and_jitter_stays_under_the_cap() -> None:
    cloud = _Backend(
        [ModelCallError("429", FailureKind.RATE_LIMIT, retry_after=4.0), _reply("from cloud")],
    )
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([]), retry_delays=(0.5,), sleeps=sleeps)
    await gateway.complete("worker", _request())
    assert sleeps == [4.0]  # the provider asked for more than the 0.5 s cap


async def test_a_provider_that_asks_for_a_very_long_wait_is_not_waited_for() -> None:
    cloud = _Backend([ModelCallError("429", FailureKind.RATE_LIMIT, retry_after=3600.0)])
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([_reply("local")]), retry_delays=(0.5, 1.5), sleeps=sleeps)
    result = await gateway.complete("worker", _request())
    assert (result.served_by, sleeps) == ("local_main", [])


def test_the_default_jitter_is_a_random_wait_between_zero_and_the_cap() -> None:
    gateway = Gateway(_catalog(), {}, env={})
    waits = {gateway._jitter(2.0) for _ in range(20)}  # the default is part of the contract
    assert len(waits) > 1
    assert all(0 <= wait <= 2.0 for wait in waits)


@pytest.mark.parametrize("kind", [FailureKind.AUTH, FailureKind.REFUSAL, FailureKind.BAD_REPLY])
async def test_a_failure_that_repeats_identically_is_not_retried(kind: FailureKind) -> None:
    cloud = _Backend([ModelCallError("no", kind)])
    sleeps: list[float] = []
    gateway = _gateway(cloud, _Backend([_reply("local")]), retry_delays=(0.5, 1.5), sleeps=sleeps)
    result = await gateway.complete("worker", _request())
    assert (result.served_by, cloud.targets, sleeps) == ("local_main", ["big"], [])


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


async def test_progress_says_when_a_request_goes_out_is_repeated_and_fails_over() -> None:
    said: list[str] = []
    cloud = _Backend([ModelCallError("busy", FailureKind.SERVER), ModelCallError("busy", FailureKind.SERVER)])
    gateway = _gateway(cloud, _Backend([_reply()]), retry_delays=(0.5,), progress=said.append)

    await gateway.complete("worker", _request())

    assert said[0] == "asking big, waiting for its reply"
    assert any(line.startswith("FAILED big:") and "retrying in" in line for line in said)
    assert any(line.startswith("FAILED big gave up") for line in said)
    assert said[-2] == "asking local_main, waiting for its reply"
    assert said[-1].startswith("local_main answered in 2s after 2 failed or repeated attempt(s)")


async def test_progress_names_a_skipped_model_and_a_chain_that_cannot_answer() -> None:
    said: list[str] = []
    gateway = _gateway(None, _Backend([ModelCallError("down")]), progress=said.append)

    with pytest.raises(GatewayError):
        await gateway.complete("worker", _request())

    assert any(line.startswith("FAILED big skipped:") for line in said)
    assert any(line.startswith("FAILED local_main gave up") for line in said)
    assert said[-1] == "FAILED no model of the 'worker' chain could answer"
