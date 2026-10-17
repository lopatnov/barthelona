"""Load ``contracts.yaml`` into a validated :class:`ContractRegistry`."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.verification import TestCase


class ContractsError(ValueError):
    """``contracts.yaml`` is unreadable or does not match the registry schema."""


def _read_yaml(path: Path) -> object:
    try:
        return YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise ContractsError(f"cannot read {path}: {exc}") from exc


def load_registry(path: Path) -> ContractRegistry:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ContractsError(f"{path}: expected a mapping at the top level")
    try:
        return ContractRegistry.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise ContractsError(f"{path}: {exc}") from exc


def load_test_cases(path: Path) -> list[TestCase]:
    """Load a YAML list of test cases (the acceptance tests of a project)."""
    data = _read_yaml(path)
    if not isinstance(data, list):
        raise ContractsError(f"{path}: expected a list of test cases at the top level")
    return _validate_test_cases(path, data)


def _validate_test_cases(path: Path, items: list[object]) -> list[TestCase]:
    try:
        return [TestCase.model_validate(item) for item in items]
    except ValueError as exc:
        raise ContractsError(f"{path}: {exc}") from exc
