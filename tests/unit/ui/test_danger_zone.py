"""The Live Run danger zone removes a run's rows and its folder, never the project folder."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest
from tests.unit.persistence.test_store import _run

from barthelona.domain import Run, RunStatus, StopReason
from barthelona.domain.layout import RUNS_DIR, run_dir
from barthelona.persistence import open_store
from barthelona.ui.danger_zone import remove_run


def test_remove_run_deletes_the_rows_and_the_run_folder_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "var").mkdir()
    project = tmp_path / "demos" / "quiz"
    project.mkdir(parents=True)
    with closing(open_store(tmp_path / "var" / "app.sqlite")) as store:
        stopped: Run = _run("r1").model_copy(
            update={"status": RunStatus.STOPPED, "stop_reason": StopReason.HUMAN_ABORT}
        )
        store.create_run(stopped)
        folder = run_dir(RUNS_DIR, "r1")
        folder.mkdir(parents=True)
        (folder / "request.txt").write_text("x", encoding="utf-8")

        remove_run(stopped, store)

        assert store.list_runs() == []
    assert not folder.exists() and project.is_dir()
