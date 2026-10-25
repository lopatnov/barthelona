"""The model gateway: role router over the catalog's chains (docs/architecture.md §16.1).

This first slice walks a chain in order, skips entries that cannot be used and falls through to the next
model when a call fails. A transient failure is repeated on the same entry first, a bounded number of times
(#255). Circuit breakers, the cost ledger and the affinity scheduler come later.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from barthelona.llm.backend import Backend, RawReply, build_completion
from barthelona.llm.catalog import Catalog, ModelTarget
from barthelona.llm.types import Completion, CompletionRequest, FailureKind, GatewayError, ModelCallError

# Seconds to wait before each repeat of a failed call on the same chain entry; the length is the retry bound.
RETRY_DELAYS = (2.0, 6.0)
# A provider that asks for a longer wait than this is treated as down for this call: the chain moves on.
MAX_RETRY_AFTER_S = 30.0
# Failures that can pass by themselves. An auth, refusal or bad-reply failure repeats identically.
_TRANSIENT = frozenset({FailureKind.SERVER, FailureKind.RATE_LIMIT, FailureKind.TRANSPORT})


class ModelGateway(Protocol):
    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        """Answer *request* with the first usable model of *role*'s chain."""
        ...


class Gateway:
    def __init__(
        self,
        catalog: Catalog,
        backends: Mapping[str, Backend],
        profile: str | None = None,
        env: Mapping[str, str] | None = None,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float], float] = lambda cap: random.uniform(0, cap),  # noqa: S311  # backoff, not security
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
        self._retry_delays = retry_delays
        self._sleep = sleep
        self._jitter = jitter

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
        for cap in (*self._retry_delays, None):
            try:
                async with self._slot(target):
                    self._say(f"asking {target.key}, waiting for its reply")
                    return await self._backends[target.provider.kind].complete(target, request), notes
            except ModelCallError as exc:
                reason = f"{exc} after {time.monotonic() - started:.1f}s [{exc.kind}]"
                if cap is None or exc.kind not in _TRANSIENT or (exc.retry_after or 0) > MAX_RETRY_AFTER_S:
                    return reason, notes
                delay = max(
                    exc.retry_after or 0.0, self._jitter(cap)
                )  # full jitter; Retry-After is the minimum
                notes.append(f"{target.key}: retry in {delay:.1f}s: {reason}")
                self._say(f"FAILED {target.key}: {reason}; retrying in {delay:.0f}s")
                await self._sleep(delay)
        raise AssertionError("unreachable: the last delay is None")  # pragma: no cover

    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        fallbacks: list[str] = []
        for target in self._catalog.resolve(role, self._profile):
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
            if self._trace is not None:
                try:
                    self._trace(role, done.model_copy(update={"prompt": request.as_text()}))
                except OSError as exc:  # the log is optional: a model answer is never lost to it
                    done = done.model_copy(
                        update={"fallbacks": (*done.fallbacks, f"reasoning log not written: {exc}")}
                    )
            return done
        self._say(f"FAILED no model of the {role!r} chain could answer")
        raise GatewayError(f"no model in the {role!r} chain could answer: " + "; ".join(fallbacks))

    @staticmethod
    def _answered(target: ModelTarget, done: Completion) -> str:
        """The progress line for a reply: who answered, how fast, and whether earlier models failed first."""
        seconds = done.record.latency_ms / 1000
        earlier = f" after {len(done.fallbacks)} failed or repeated attempt(s)" if done.fallbacks else ""
        return f"{target.key} answered in {seconds:.0f}s{earlier}"
