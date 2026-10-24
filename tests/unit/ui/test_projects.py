from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.domain import Run, RunBudget
from barthelona.domain.presets import builtin_presets
from barthelona.ui.projects import existing_projects, project_problem


def test_existing_projects_lists_the_subfolders_only(tmp_path: Path) -> None:
    (tmp_path / "hello").mkdir()
    (tmp_path / "fizzbuzz").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "README.md").write_text("not a folder", encoding="utf-8")
    assert existing_projects(tmp_path) == ["fizzbuzz", "hello"]
    assert existing_projects(tmp_path / "missing") == []


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", False),
        ("my-program", False),
        ("hello", True),
        ("Bad Name", True),
        ("-lead", True),
        ("a" * 65, True),
    ],
)
def test_a_new_name_must_be_a_free_slug(name: str, problem: bool) -> None:
    assert (project_problem(name, ["hello"]) is not None) is problem


def _run(**extra: object) -> Run:
    return Run(
        id="r1",
        mode="create",
        workspace="workspaces/r1",
        target=builtin_presets()[0],
        policy_version="v1",
        budget=RunBudget(wall_s=60.0, tokens=1000),
        **extra,
    )


def test_the_run_keeps_a_valid_project_and_defaults_to_none() -> None:
    assert _run().project is None
    run = _run(project="my-program")
    assert Run.model_validate_json(run.model_dump_json()).project == "my-program"
    with pytest.raises(ValueError, match="project"):
        _run(project="Not A Slug")


def _page() -> None:
    from barthelona.ui.pages.new_request import page_new_request

    page_new_request()


def test_the_page_has_a_project_folder_field_and_lists_the_taken_folders() -> None:
    app = AppTest.from_function(_page, default_timeout=60).run()
    assert not app.exception
    field = next(box for box in app.text_input if box.label == "Project folder (optional)")
    assert field.value == ""
    assert any("Existing folders in demos/" in expander.label for expander in app.expander)


def test_submitting_an_existing_folder_name_is_refused_and_creates_no_run() -> None:
    app = AppTest.from_function(_page, default_timeout=60).run()
    taken = existing_projects()[0]
    next(area for area in app.text_area if area.label == "Prompt").set_value("Print hello.")
    next(box for box in app.text_input if box.label == "Project folder (optional)").set_value(taken)
    app.button[0].click().run()
    assert any("already exists" in error.value for error in app.error)
    assert not any("Run created" in success.value for success in app.success)
