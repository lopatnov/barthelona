"""Continue a run that stopped on a limit."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.domain import (
    CommandKind,
    Profile,
    Run,
    RunBudget,
    RunMode,
    RunStatus,
    StopReason,
)
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store
from barthelona.ui.continue_run import EXTRA_WALL_S, can_continue, extended_budget


def _run(reason: StopReason | None, usd: float | None = None) -> Run:
    return Run(
        id="run-1",
        mode=RunMode.CREATE,
        workspace="demos/hello-demo",
        target=builtin_presets()[0],
        profile=Profile.METERLESS,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=400000, usd=usd, max_sprints=10, cloud_allowed=True),
        status=RunStatus.STOPPED if reason else RunStatus.RUNNING,
        stop_reason=reason,
    )


def test_only_a_run_stopped_by_a_limit_can_be_continued() -> None:
    assert can_continue(_run(StopReason.BUDGET_TIME))
    assert can_continue(_run(StopReason.BUDGET_TOKENS))
    assert not can_continue(_run(StopReason.MAX_ATTEMPTS))
    assert not can_continue(_run(StopReason.HUMAN_ABORT))
    assert not can_continue(_run(None))


def test_the_limit_that_ran_out_is_raised_and_the_others_stay() -> None:
    by_time = extended_budget(_run(StopReason.BUDGET_TIME))
    by_tokens = extended_budget(_run(StopReason.BUDGET_TOKENS))
    by_money = extended_budget(_run(StopReason.BUDGET_COST, usd=2.0))

    assert (by_time.wall_s, by_time.tokens) == (3600 + EXTRA_WALL_S, 400000)
    assert (by_tokens.wall_s, by_tokens.tokens) == (3600, 800000)
    assert by_money.usd == 4.0 and by_money.tokens == 400000


def _page() -> None:
    from barthelona.ui.pages.live_run import page_live_run

    page_live_run()


def _store_with(root: Path, run: Run) -> None:
    (root / "var" / "runs" / run.id).mkdir(parents=True)
    store = open_store(root / "var" / "app.sqlite")
    store.create_run(run.model_copy(update={"status": RunStatus.QUEUED, "stop_reason": None}))
    if run.stop_reason is not None:
        store.set_run_status(run.id, RunStatus.STOPPED, run.stop_reason)
    store.close()


def test_the_continue_button_queues_a_larger_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _store_with(tmp_path, _run(StopReason.BUDGET_TIME))
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False
    app.run()

    button = next(b for b in app.button if b.label.startswith("▶️ Continue"))
    assert "4 hours" in button.label
    button.click().run()

    store = open_store(tmp_path / "var" / "app.sqlite")
    waiting = store.runs_to_continue()
    commands = store.claim_commands("run-1")
    store.close()
    assert [run.id for run in waiting] == ["run-1"]
    assert [c.kind for c in commands] == [CommandKind.EXTEND_BUDGET]
    assert commands[0].budget is not None and commands[0].budget.wall_s == 3600 + EXTRA_WALL_S
    assert not app.exception


def test_a_running_run_has_no_extend_or_continue_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store_with(tmp_path, _run(None))
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not [b for b in app.button if "Continue" in b.label or "Extend" in b.label]
    assert not app.exception
