"""Load ``contracts.yaml`` into a validated :class:`ContractRegistry`."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from barthelona.domain.contracts import ContractRegistry


class ContractsError(ValueError):
    """``contracts.yaml`` is unreadable or does not match the registry schema."""


def load_registry(path: Path) -> ContractRegistry:
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise ContractsError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractsError(f"{path}: expected a mapping at the top level")
    try:
        return ContractRegistry.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise ContractsError(f"{path}: {exc}") from exc
