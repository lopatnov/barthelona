"""A bench task on disk: ``task.yaml``, ``contracts.yaml``, ``hidden/tests.yaml`` (architecture §20).

The hidden tests are the oracle and never enter a prompt; the model sees the prompt, the contracts and the
generated include file only.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from barthelona.contracts.loader import load_registry, load_test_cases
from barthelona.domain._base import DomainModel, ItemId, ShortText, Text
from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import Dialect, Level
from barthelona.domain.verification import TestCase

DEFAULT_LEVELS = (Level.V0, Level.V1, Level.V2, Level.V5)


class BenchError(ValueError):
    """A task directory is unreadable or invalid."""


class BenchTask(DomainModel):
    id: ItemId
    title: ShortText
    dialect: Dialect
    prompt: Text
    module: ItemId  # source stem: the model writes `<module><extension>`
    required_levels: tuple[Level, ...] = DEFAULT_LEVELS
    registry: ContractRegistry
    contracts_text: str
    tests: tuple[TestCase, ...]


def load_task(directory: Path) -> BenchTask:
    """Read ``directory`` into a validated task; `BenchError` names the file that is wrong."""
    try:
        meta = YAML(typ="safe").load((directory / "task.yaml").read_text(encoding="utf-8"))
        contracts_file = directory / "contracts.yaml"
        return BenchTask.model_validate(
            {
                **meta,
                "registry": load_registry(contracts_file),
                "contracts_text": contracts_file.read_text(encoding="utf-8"),
                "tests": load_test_cases(directory / "hidden" / "tests.yaml"),
            }
        )
    except (OSError, YAMLError, TypeError, ValidationError, ValueError) as exc:
        raise BenchError(f"{directory}: {exc}") from exc


def load_suite(root: Path, suite: str, dialect: str = "nasm") -> list[BenchTask]:
    """All tasks of ``root/tasks/<suite>/<dialect>/``, sorted by id."""
    directory = root / "tasks" / suite / dialect
    if not directory.is_dir():
        raise BenchError(f"{directory} is not a directory")
    return sorted((load_task(path) for path in directory.iterdir() if path.is_dir()), key=lambda t: t.id)
