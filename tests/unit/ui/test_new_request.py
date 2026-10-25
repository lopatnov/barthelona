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


def _page() -> None:
    from barthelona.ui.pages.new_request import page_new_request

    page_new_request()


def test_the_new_project_box_decides_between_a_name_field_and_the_existing_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.testing.v1 import AppTest

    (tmp_path / "demos" / "a-demo").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page).run()

    assert app.checkbox[0].label == "New project" and app.checkbox[0].value is True
    assert [box.label for box in app.text_input] == ["Project"]
    assert not any(box.label == "Project" for box in app.selectbox)

    app.checkbox[0].uncheck().run()

    assert [box.label for box in app.selectbox if box.label == "Project"] == ["Project"]
    assert not app.text_input


def test_a_run_is_created_with_auto_approve_on_unless_the_box_is_unticked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import closing

    from streamlit.testing.v1 import AppTest

    from barthelona.persistence import open_store

    monkeypatch.chdir(tmp_path)
    (tmp_path / "var").mkdir()
    app = AppTest.from_function(_page).run()
    box = next(box for box in app.checkbox if box.label == "Approve checkpoints automatically")
    assert box.value is True

    app.text_input[0].set_value("quiz-demo")
    app.text_area[0].set_value("Print hello.")
    app.button[0].click().run()
    box = next(box for box in app.checkbox if box.label == "Approve checkpoints automatically")
    box.uncheck()
    app.button[0].click().run()

    with closing(open_store(tmp_path / "var" / "app.sqlite")) as store:
        runs = store.list_runs()
    assert sorted(run.auto_approve for run in runs) == [False, True]
    assert not any(run.auto_package for run in runs)  # unticked by default


def test_open_page_does_nothing_when_no_pages_are_registered() -> None:
    from streamlit.testing.v1 import AppTest

    def page() -> None:
        from barthelona.ui.navigation import open_page

        open_page("live_run")  # would raise if it tried to switch without a registered page

    assert not AppTest.from_function(page).run().exception
