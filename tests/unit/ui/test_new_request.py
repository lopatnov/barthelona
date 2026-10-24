"""The New Request page's form checks and the demos/ folder list."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.ui.pages import new_request


@pytest.mark.parametrize("folder", ["simplest-demo", "demo2", "a"])
def test_a_prompt_and_a_clean_folder_name_make_a_run(folder: str) -> None:
    assert new_request._form_problem("Print hello.", folder) is None


@pytest.mark.parametrize("folder", ["", "Demo", "-demo", "my demo", "../x", "a/b", "x" * 42])
def test_a_folder_name_that_is_not_a_plain_slug_is_refused(folder: str) -> None:
    assert "Folder name" in (new_request._form_problem("Print hello.", folder) or "")


def test_an_empty_prompt_is_refused_first() -> None:
    assert new_request._form_problem("  ", "demo") == "Prompt cannot be empty."


def test_the_folder_list_is_the_sorted_subfolders_of_demos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "demos" / "b-demo").mkdir(parents=True)
    (tmp_path / "demos" / "a-demo").mkdir()
    (tmp_path / "demos" / "README.md").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert new_request._demo_folders() == ["a-demo", "b-demo"]


def test_a_missing_demos_directory_gives_an_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert new_request._demo_folders() == []
