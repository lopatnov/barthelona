"""Load ``config/models.yaml`` into a validated catalog and resolve a role chain (architecture §16.2).

Only the parts the gateway acts on are modelled; prices, budgets and resilience settings are ignored until
the ledger and the breakers land.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from barthelona.domain.run import ProviderId

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_LOCALHOST = re.compile(r"//localhost[:/]", re.IGNORECASE)

ModelKey = Annotated[str, StringConstraints(min_length=1, max_length=128)]
ChainParam = str | int | float | bool


class CatalogError(ValueError):
    """``models.yaml`` is unreadable, invalid or has no usable chain."""


class _Entry(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class ProviderConfig(_Entry):
    kind: Literal["openai_chat", "openai_responses", "anthropic_messages", "gemini_native"]
    base_url: str = ""
    api_key_env: str | None = None
    local: bool = False
    enabled: bool = True
    max_concurrency: int = Field(default=1, ge=1)
    structured_output: Literal["json_schema", "json_object", "output_config", "none"] = "none"
    timeout_s: float = Field(default=900, gt=0)
    headers: dict[str, str] = Field(default_factory=dict)  # fixed request headers, never secrets
    plain_chat: bool = False  # a cloud gateway that needs no reasoning parameters


class ModelConfig(_Entry):
    provider: ProviderId
    model: ModelKey
    price_class: str
    context: int | None = Field(default=None, ge=1)  # embedding models have none
    enabled: bool = True
    strip_think: bool = False


class ChainEntry(_Entry):
    """A chain item: a model key plus per-role parameters such as ``effort`` (§16.2)."""

    model: ModelKey
    params: dict[str, ChainParam] = Field(default_factory=dict)

    @classmethod
    def parse(cls, raw: object) -> ChainEntry:
        if isinstance(raw, str):
            return cls(model=raw)
        if isinstance(raw, dict) and isinstance(raw.get("model"), str):
            return cls(model=raw["model"], params={k: v for k, v in raw.items() if k != "model"})
        raise CatalogError(f"chain entry must be a model key or a mapping with 'model': {raw!r}")


class ModelTarget(_Entry):
    """A resolved chain entry: everything a backend needs to make one call."""

    key: ModelKey
    provider_id: ProviderId
    provider: ProviderConfig
    model: ModelConfig
    params: dict[str, ChainParam] = Field(default_factory=dict)


class Catalog(_Entry):
    providers: dict[ProviderId, ProviderConfig]
    models: dict[ModelKey, ModelConfig]
    profiles: dict[str, dict[str, list[ChainEntry]]]
    default_profile: str

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for key, model in self.models.items():
            if model.provider not in self.providers:
                raise ValueError(f"model {key!r} names unknown provider {model.provider!r}")
        for provider_id, provider in self.providers.items():
            if provider.local and _LOCALHOST.search(provider.base_url):
                raise ValueError(
                    f"provider {provider_id!r}: use 127.0.0.1, not localhost (IPv6 resolution hangs)"
                )
        for profile, roles in self.profiles.items():
            for role, chain in roles.items():
                self._check_chain(profile, role, chain)
        if self.default_profile not in self.profiles:
            raise ValueError(f"default_profile {self.default_profile!r} is not a profile")
        return self

    def _check_chain(self, profile: str, role: str, chain: list[ChainEntry]) -> None:
        where = f"profile {profile!r} role {role!r}"
        if not chain:
            raise ValueError(f"{where}: empty chain")
        unknown = [entry.model for entry in chain if entry.model not in self.models]
        if unknown:
            raise ValueError(f"{where}: unknown model {unknown[0]!r}")
        if not self.providers[self.models[chain[-1].model].provider].local:
            raise ValueError(f"{where}: the chain must end in a local model (invariant 11)")

    def resolve(self, role: str, profile: str | None = None) -> list[ModelTarget]:
        """The chain of *role* under *profile* (default profile when omitted), in order."""
        name = profile or self.default_profile
        try:
            chain = self.profiles[name][role]
        except KeyError:
            raise CatalogError(f"no chain for role {role!r} in profile {name!r}") from None
        return [self._target(entry) for entry in chain]

    def _target(self, entry: ChainEntry) -> ModelTarget:
        model = self.models[entry.model]
        return ModelTarget(
            key=entry.model,
            provider_id=model.provider,
            provider=self.providers[model.provider],
            model=model,
            params=entry.params,
        )


def expand_env(value: str, env: Mapping[str, str]) -> str:
    """Resolve ``${VAR}`` and ``${VAR:-default}``; a missing variable without a default becomes empty."""

    def replace(match: re.Match[str]) -> str:
        return env.get(match.group(1)) or match.group(2) or ""

    return _ENV_REFERENCE.sub(replace, value)


def _expand_base_urls(data: dict[str, Any], env: Mapping[str, str]) -> None:
    for provider in data.get("providers", {}).values():
        if isinstance(provider, dict) and isinstance(provider.get("base_url"), str):
            provider["base_url"] = expand_env(provider["base_url"], env)


def _normalize_profiles(data: dict[str, Any]) -> None:
    data["profiles"] = {
        profile: {role: [ChainEntry.parse(raw) for raw in chain] for role, chain in roles.items()}
        for profile, roles in data.get("profiles", {}).items()
    }


def load_catalog(path: Path, env: Mapping[str, str] | None = None) -> Catalog:
    """Read and validate the catalog. `env` defaults to the process environment (only for ``base_url``)."""
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: expected a mapping at the top level")
    _expand_base_urls(data, os.environ if env is None else env)
    try:
        _normalize_profiles(data)
        return Catalog.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError and CatalogError are ValueErrors
        raise CatalogError(f"{path}: {exc}") from exc
