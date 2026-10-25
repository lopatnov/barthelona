"""The stage line and the approval banner of Live Run."""

from __future__ import annotations

from barthelona.ui.run_info import stage_line


def test_done_stages_are_ticked_and_the_next_one_is_in_progress() -> None:
    line = stage_line({"preflight", "intake"}, active=True)

    assert line.startswith("✅ Preflight  →  ✅ Understand the request  →  ⏳ Write the specification")
    assert line.endswith("◻️ Finish")


def test_a_run_that_is_not_active_has_no_stage_in_progress() -> None:
    assert "⏳" not in stage_line({"preflight"}, active=False)


def test_a_finished_run_shows_every_stage_done() -> None:
    nodes = {"preflight", "intake", "spec", "test_author", "validate_spec", "g1_gate", "codegen", "g4_gate"}

    line = stage_line(nodes | {"finalize"}, active=False)

    assert "◻️" not in line and line.count("✅") == 9


def test_the_file_rows_say_which_files_exist_and_which_are_not_yet(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from barthelona.ui.run_info import file_rows

    (tmp_path / "request.txt").write_text("hi", encoding="utf-8")

    rows = {name: state for name, state, _ in file_rows(tmp_path)}

    assert rows["request.txt"].startswith("2 bytes")
    assert rows["main.asm"] == "not yet" and rows["spec.json"] == "not yet"
