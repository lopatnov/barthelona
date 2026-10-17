"""The bench's verifier: the oracle ladder run on one staged task (architecture §13, §20)."""

from __future__ import annotations

from pathlib import Path

from barthelona.bench.task import BenchTask
from barthelona.domain.enums import Dialect
from barthelona.domain.verification import LevelResult
from barthelona.executors import AgentExecutor
from barthelona.toolchains import GasAttAdapter, GasIntelAdapter, NasmAdapter
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.verification import LadderOptions, run_ladder


def adapter_for(dialect: Dialect) -> DialectAdapter:
    adapters: dict[Dialect, type[DialectAdapter]] = {
        Dialect.NASM: NasmAdapter,
        Dialect.GAS_INTEL: GasIntelAdapter,
        Dialect.GAS_ATT: GasAttAdapter,
    }
    if dialect not in adapters:
        raise ValueError(f"no dialect adapter for {dialect!r}; the bench supports {', '.join(adapters)}")
    return adapters[dialect]()


class LadderVerifier:
    """Runs the ladder up to the task's highest required level; the hidden tests are the V5 oracle."""

    def __init__(self, executor: AgentExecutor) -> None:
        self._executor = executor
        self._sandbox = executor.sandbox()

    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]:
        options = LadderOptions(contracts=task.registry, tests=list(task.tests), sandbox=self._sandbox)
        return await run_ladder(
            max(task.required_levels),
            self._executor,
            adapter_for(task.dialect),
            sources,
            run_id,
            attempt,
            options,
        )
