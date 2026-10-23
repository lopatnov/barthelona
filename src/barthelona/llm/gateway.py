"""The model gateway: role router over the catalog's chains (docs/architecture.md §16.1).

This first slice walks a chain in order, skips entries that cannot be used and falls through to the next
model when a call fails. Circuit breakers, retries, the cost ledger and the affinity scheduler come later.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping
from typing import Protocol

from barthelona.llm.backend import Backend, RawReply, build_completion
from barthelona.llm.catalog import Catalog, ModelTarget
from barthelona.llm.types import Completion, CompletionRequest, GatewayError, ModelCallError


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
    ) -> None:
        self._catalog = catalog
        self._backends = backends
        self._profile = profile
        self._env = os.environ if env is None else env
        self._slots: dict[str, asyncio.Semaphore] = {}

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

    async def _call(self, target: ModelTarget, request: CompletionRequest) -> RawReply | str:
        """The backend's reply, or the reason this entry failed."""
        started = time.monotonic()
        try:
            async with self._slot(target):
                return await self._backends[target.provider.kind].complete(target, request)
        except ModelCallError as exc:
            return f"{exc} after {time.monotonic() - started:.1f}s"

    async def complete(self, role: str, request: CompletionRequest) -> Completion:
        fallbacks: list[str] = []
        for target in self._catalog.resolve(role, self._profile):
            if (reason := self._unusable(target)) is not None:
                fallbacks.append(f"{target.key}: {reason}")
                continue
            outcome = await self._call(target, request)
            if isinstance(outcome, str):
                fallbacks.append(f"{target.key}: {outcome}")
                continue
            return build_completion(target, request, outcome, tuple(fallbacks))
        raise GatewayError(f"no model in the {role!r} chain could answer: " + "; ".join(fallbacks))
