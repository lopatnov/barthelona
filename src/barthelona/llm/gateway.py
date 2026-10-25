"""The model gateway: role router over the catalog's chains (docs/architecture.md §16.1).

This first slice walks a chain in order, skips entries that cannot be used and falls through to the next
model when a call fails. A transient failure (5xx, rate limit, connection reset, a timeout) is repeated on
the same entry first, as often as ``resilience.retry`` in the catalog allows. Circuit breakers, the cost
ledger and the affinity scheduler come later.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable, Collection, Mapping
from typing import Protocol

from barthelona.llm.backend import Backend, RawReply, build_completion
from barthelona.llm.catalog import Catalog, ModelTarget
from barthelona.llm.types import Completion, CompletionRequest, FailureKind, GatewayError, ModelCallError

# Failures that can pass by themselves. A timeout is a stall, not a refusal: a reasoning lane that went
# quiet for the whole read timeout usually answers on the repeat, so it is retried like a 5xx. An auth,
# refusal or bad-reply failure would repeat identically and moves the chain on at once.
_TRANSIENT = frozenset(
    {FailureKind.SERVER, FailureKind.RATE_LIMIT, FailureKind.TRANSPORT, FailureKind.TIMEOUT}
)
# A stall costs the whole read timeout (300 s for Meterless), so it is repeated once even when the catalog
# allows more attempts: a second silence is a down lane, not a hiccup, and the chain should move on.
_MAX_TIMEOUT_RETRIES = 1


def _full_jitter(cap: float) -> float:
    """A random wait below the cap, so callers that stalled together do not retry together."""
    return random.uniform(0, cap)  # noqa: S311  # backoff, not security


def _no_jitter(cap: float) -> float:
    """The cap itself: ``jitter: none`` in the catalog uses the configured delays unchanged."""
    return cap


class ModelGateway(Protocol):
    async def complete(
        self, role: str, request: CompletionRequest, avoid: Collection[str] = ()
    ) -> Completion:
        """Answer *request* with the first usable model of *role*'s chain.

        *avoid* names the catalog keys whose last reply the caller could not use (a model that answered,
        but with prose or code where the step needs JSON). They are skipped like a disabled provider, so a
        lane that ignores the output protocol yields to the next entry of the chain instead of ending the
        run: §16.3 asks for "the next tier" after the repairs, and this is how a caller reaches it.
        """
        ...


class Gateway:
    def __init__(
        self,
        catalog: Catalog,
        backends: Mapping[str, Backend],
        profile: str | None = None,
        env: Mapping[str, str] | None = None,
        retry_delays: tuple[float, ...] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float], float] | None = None,
        trace: Callable[[str, Completion], None] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._trace = trace  # the optional reasoning log, called once per answered request
        self._progress = progress  # told in words when a request goes out, is repeated or fails over
        self._catalog = catalog
        self._backends = backends
        self._profile = profile
        self._env = os.environ if env is None else env
        self._slots: dict[str, asyncio.Semaphore] = {}
        self._retry = catalog.resilience.retry  # the catalog's policy, not a constant in this file
        self._retry_delays = self._retry.delays() if retry_delays is None else retry_delays
        self._sleep = sleep
        self._jitter = jitter or (_full_jitter if self._retry.jitter == "full" else _no_jitter)

    def _unusable(self, target: ModelTarget) -> str | None:
        provider = target.provider
        if not provider.enabled or not target.model.enabled:
            return "disabled"
        if provider.api_key_env and not self._env.get(provider.api_key_env):
            return f"{provider.api_key_env} is not set"
        if provider.api_key_env and self._env.get(provider.api_key_env) in provider.rejected_keys:
            return f"{provider.api_key_env} holds a placeholder the server rejects"
        backend = self._backends.get(provider.kind)
        if backend is None:
            return f"no backend for {provider.kind}"
        return backend.unsupported(target)

    def _slot(self, target: ModelTarget) -> asyncio.Semaphore:
        if target.provider_id not in self._slots:
            self._slots[target.provider_id] = asyncio.Semaphore(target.provider.max_concurrency)
        return self._slots[target.provider_id]

    def _say(self, message: str) -> None:
        if self._progress is not None:
            self._progress(message)

    async def _call(
        self, target: ModelTarget, request: CompletionRequest
    ) -> tuple[RawReply | str, list[str]]:
        """The backend's reply or the reason this entry failed, with a note for each repeated call."""
        started = time.monotonic()
        notes: list[str] = []
        stalls = 0
        for cap in (*self._retry_delays, None):
            try:
                async with self._slot(target):
                    self._say(f"asking {target.key}, waiting for its reply")
                    return await self._backends[target.provider.kind].complete(target, request), notes
            except ModelCallError as exc:
                reason = f"{exc} after {time.monotonic() - started:.1f}s [{exc.kind}]"
                stalls += exc.kind is FailureKind.TIMEOUT
                asked = exc.retry_after if self._retry.honor_retry_after else None
                if (
                    cap is None
                    or exc.kind not in _TRANSIENT
                    or stalls > _MAX_TIMEOUT_RETRIES
                    or (asked or 0.0) > self._retry.max_delay_s
                ):
                    return reason, notes  # nothing can be gained by waiting: the chain moves on
                delay = max(asked or 0.0, self._jitter(cap))  # Retry-After is the minimum wait
                notes.append(f"{target.key}: retry in {delay:.1f}s: {reason}")
                self._say(f"FAILED {target.key}: {reason}; retrying in {delay:.0f}s")
                await self._sleep(delay)
        raise AssertionError("unreachable: the last delay is None")  # pragma: no cover

    async def complete(
        self, role: str, request: CompletionRequest, avoid: Collection[str] = ()
    ) -> Completion:
        fallbacks: list[str] = []
        for target in self._catalog.resolve(role, self._profile):
            if target.key in avoid:
                fallbacks.append(f"{target.key}: skipped, its last reply was unusable")
                self._say(f"FAILED {target.key} skipped: its last reply was unusable")
                continue
            if (reason := self._unusable(target)) is not None:
                fallbacks.append(f"{target.key}: {reason}")
                self._say(f"FAILED {target.key} skipped: {reason}")
                continue
            outcome, notes = await self._call(target, request)
            fallbacks.extend(notes)
            if isinstance(outcome, str):
                fallbacks.append(f"{target.key}: {outcome}")
                self._say(f"FAILED {target.key} gave up: {outcome}")
                continue
            done = build_completion(target, request, outcome, tuple(fallbacks))
            self._say(self._answered(target, done))
            return self._traced(role, request, done)
        self._say(f"FAILED no model of the {role!r} chain could answer")
        raise GatewayError(f"no model in the {role!r} chain could answer: " + "; ".join(fallbacks))

    def _traced(self, role: str, request: CompletionRequest, done: Completion) -> Completion:
        """Write the reasoning log entry; a log that cannot be written is noted, never a lost answer."""
        if self._trace is None:
            return done
        try:
            self._trace(role, done.model_copy(update={"prompt": request.as_text()}))
        except OSError as exc:
            return done.model_copy(
                update={"fallbacks": (*done.fallbacks, f"reasoning log not written: {exc}")}
            )
        return done

    @staticmethod
    def _answered(target: ModelTarget, done: Completion) -> str:
        """The progress line for a reply: who answered, how fast, and whether earlier models failed first."""
        seconds = done.record.latency_ms / 1000
        earlier = f" after {len(done.fallbacks)} failed or repeated attempt(s)" if done.fallbacks else ""
        return f"{target.key} answered in {seconds:.0f}s{earlier}"
