"""Remove a stopped run from Live Run, behind a confirmation."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.domain import Profile, Run, RunBudget, RunMode, RunStatus, StopReason
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store
from barthelona.ui.danger_zone import can_remove


def _run(status: RunStatus, reason: StopReason | None = None) -> Run:
    return Run(
        id="run-1",
        mode=RunMode.CREATE,
        workspace="demos/hello-demo",
        target=builtin_presets()[0],
        profile=Profile.METERLESS,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=400000, max_sprints=10, cloud_allowed=True),
        status=status,
        stop_reason=reason,
        auto_approve=True,
        auto_package=False,
    )


def test_only_a_stopped_run_can_be_removed() -> None:
    assert can_remove(_run(RunStatus.STOPPED, StopReason.HUMAN_ABORT))
    for status in (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING_GATE):
        assert not can_remove(_run(status))


def _page() -> None:
    from barthelona.ui.pages.live_run import page_live_run

    page_live_run()


def _setup(root: Path, status: RunStatus, reason: StopReason | None = None) -> None:
    folder = root / "var" / "runs" / "run-1"
    folder.mkdir(parents=True)
    (folder / "request.txt").write_text("hi", encoding="utf-8")
    project = root / "demos" / "hello-demo"
    project.mkdir(parents=True)
    (project / "keep.txt").write_text("mine", encoding="utf-8")
    store = open_store(root / "var" / "app.sqlite")
    store.create_run(_run(RunStatus.QUEUED))
    if status is not RunStatus.QUEUED:
        store.set_run_status("run-1", status, reason)
    store.close()


def test_removing_a_stopped_run_needs_the_confirmation_and_keeps_the_project_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, RunStatus.STOPPED, StopReason.HUMAN_ABORT)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False
    app.run()

    button = next(b for b in app.button if "Remove run" in b.label)
    assert button.disabled  # not before the box is ticked
    next(c for c in app.checkbox if "I understand" in c.label).check().run()
    next(b for b in app.button if "Remove run" in b.label).click().run()

    store = open_store(tmp_path / "var" / "app.sqlite")
    assert store.list_runs() == []
    store.close()
    assert not (tmp_path / "var" / "runs" / "run-1").exists()
    assert (tmp_path / "demos" / "hello-demo" / "keep.txt").read_text(encoding="utf-8") == "mine"
    assert not app.exception


def test_a_running_run_cannot_be_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(tmp_path, RunStatus.RUNNING)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not [b for b in app.button if "Remove run" in b.label]
    assert any("Cancel Run" in box.value and "first" in box.value for box in app.info)
    assert not app.exception


def test_run_parameters_show_the_automatic_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(tmp_path, RunStatus.STOPPED, StopReason.MAX_ATTEMPTS)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    text = " ".join(item.value for item in app.markdown)
    assert (
        "approve checkpoints automatically: yes" in text
        and "write the project into demos/ when green: no" in text
    )
