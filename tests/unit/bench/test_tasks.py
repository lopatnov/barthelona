"""The shipped dev bench tasks load, are self-consistent and keep their oracle out of the prompt."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.bench import BenchError, load_prompts, load_suite, load_task
from barthelona.bench.prompts import render_first_prompt
from barthelona.domain.contracts import SymbolKind
from barthelona.domain.verification import TestKind

BENCH = Path(__file__).resolve().parents[3] / "bench"
TASKS = load_suite(BENCH, "dev")


def test_the_dev_suite_has_ten_tasks_with_unique_ids() -> None:
    ids = [task.id for task in TASKS]
    assert len(ids) == 10
    assert len(set(ids)) == 10


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.id)
def test_each_task_is_one_function_with_c_harness_cases(task) -> None:  # type: ignore[no-untyped-def]  # parametrised
    assert list(task.registry.symbols) == [task.module]
    assert task.registry.symbols[task.module].kind == SymbolKind.FUNC
    assert task.tests
    assert all(case.kind == TestKind.C_HARNESS and case.symbol == task.module for case in task.tests)


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.id)
def test_the_prompt_shows_the_contract_and_include_but_no_hidden_case(task) -> None:  # type: ignore[no-untyped-def]  # parametrised
    prompt = render_first_prompt(load_prompts(BENCH), task, f"{task.module}.asm")
    assert f"global {task.module}" in prompt
    assert f'%include "gen/{task.module}.inc"' in prompt
    assert not any(case.id in prompt for case in task.tests)
    assert not any(
        str(case.expect.ret) in prompt
        for case in task.tests
        if case.expect.ret is not None and case.expect.ret > 1000
    )


def test_a_missing_task_directory_names_itself(tmp_path: Path) -> None:
    with pytest.raises(BenchError, match="nothing"):
        load_task(tmp_path / "nothing")
