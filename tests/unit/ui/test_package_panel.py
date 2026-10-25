"""The Package panel: when the button may run, which files block it, and the commit lookup."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from barthelona.domain import Run, StopReason
from barthelona.ui import package_panel

SHA = "d76afc5ed3f5611bff1f7594035a1fbc4ac65686"


class _Stopped:
    def __init__(self, reason: StopReason | None) -> None:
        self.stop_reason = reason


def _run(reason: StopReason | None = StopReason.GREEN) -> Run:
    return cast(Run, _Stopped(reason))


def test_a_green_run_with_a_clean_folder_and_a_sha_may_be_packaged(tmp_path: Path) -> None:
    assert package_panel.package_problem(_run(), tmp_path / "demos" / "x", SHA) is None


def test_a_run_that_did_not_stop_green_is_refused() -> None:
    problem = package_panel.package_problem(_run(StopReason.MAX_ATTEMPTS), Path("demos/x"), SHA)
    assert problem is not None
    assert "green" in problem


def test_a_run_without_a_demos_folder_is_refused() -> None:
    assert "demos/ folder" in (package_panel.package_problem(_run(), None, SHA) or "")


@pytest.mark.parametrize("ref", ["", "abc", "x" * 39])
def test_a_commit_sha_that_is_not_40_characters_is_refused(ref: str) -> None:
    assert "40-character" in (package_panel.package_problem(_run(), Path("demos/x"), ref) or "")


def test_a_folder_that_already_has_files_is_refused(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.asm").write_text("x", encoding="utf-8")
    problem = package_panel.package_problem(_run(), tmp_path, SHA)
    assert problem is not None
    assert "src/main.asm" in problem.replace("\\", "/")


def test_existing_files_of_a_missing_folder_is_empty(tmp_path: Path) -> None:
    assert package_panel.existing_files(tmp_path / "nope") == []


def _fake_git(stdout: str, code: int) -> Any:
    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], code, stdout=stdout)

    return run


def test_current_commit_reads_git_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_git(SHA + "\n", 0))
    assert package_panel.current_commit() == SHA


@pytest.mark.parametrize(("stdout", "code"), [("", 128), ("not-a-sha", 0)])
def test_current_commit_is_empty_when_git_cannot_answer(
    monkeypatch: pytest.MonkeyPatch, stdout: str, code: int
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_git(stdout, code))
    assert package_panel.current_commit() == ""
