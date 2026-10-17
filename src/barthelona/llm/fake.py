"""FakeGateway: scripted replies for engine and graph tests (no network)."""

from __future__ import annotations

from collections.abc import Iterable

from barthelona.llm.backend import RawReply, build_completion
from barthelona.llm.catalog import ModelConfig, ModelTarget, ProviderConfig
from barthelona.llm.types import Completion, CompletionRequest, GatewayError

_TARGET = ModelTarget(
    key="fake",
    provider_id="fake",
    provider=ProviderConfig(kind="openai_chat", local=True),
    model=ModelConfig(
        provider="fake", model="fake-model", price_class="local", context=16384, strip_think=True
    ),
)


class FakeGateway:
    """Answers each call with the next scripted item: text, or an exception to raise."""

    def __init__(self, script: Iterable[str | Exception]) -> None:
        self._script = list(script)
        self.calls: list[tuple[str, CompletionRequest]] = []

    async def complete(self, role: str, request: CompletionRequest) -> Completion:  # NOSONAR S7503: protocol
        self.calls.append((role, request))
        if len(self.calls) > len(self._script):
            raise GatewayError(f"FakeGateway script exhausted at call {len(self.calls)} (role {role!r})")
        item = self._script[len(self.calls) - 1]
        if isinstance(item, Exception):
            raise item
        reply = RawReply(
            text=item, tokens_in=0, tokens_out=len(item.split()), stop_reason="stop", latency_ms=0
        )
        return build_completion(_TARGET, request, reply)
