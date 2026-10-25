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


def test_the_stage_a_run_stopped_in_is_marked_failed_not_done() -> None:
    line = stage_line({"preflight", "codegen"}, active=False, failed="codegen")

    assert "❌ Write and check the program" in line and "✅ Preflight" in line


def test_automatic_approvals_are_labeled_as_the_workers() -> None:
    line = stage_line(set(), active=False, automatic=True)

    assert "Automatic approval: G1" in line and "Automatic approval: G4" in line
    assert "Your approval" not in line


def test_the_failed_stage_is_the_last_one_done_unless_the_run_is_green_or_unfinished() -> None:
    from barthelona.domain import RunStatus, StopReason
    from barthelona.ui.run_info import _failed_stage

    class _Run:
        def __init__(self, status: RunStatus, reason: StopReason | None) -> None:
            self.status, self.stop_reason = status, reason

    done = {"preflight", "intake", "finalize"}
    assert _failed_stage(_Run(RunStatus.STOPPED, StopReason.MAX_ATTEMPTS), done) == "intake"  # type: ignore[arg-type]
    assert _failed_stage(_Run(RunStatus.STOPPED, StopReason.GREEN), done) is None  # type: ignore[arg-type]
    assert _failed_stage(_Run(RunStatus.RUNNING, None), done) is None  # type: ignore[arg-type]


def test_every_code_attempt_gets_its_own_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from barthelona.ui.run_info import file_rows

    (tmp_path / "attempt-1.asm").write_text("a", encoding="utf-8")
    (tmp_path / "attempt-2.asm").write_text("bb", encoding="utf-8")

    names = [name for name, state, _ in file_rows(tmp_path) if state != "not yet"]

    assert names == ["attempt-1.asm", "attempt-2.asm"]
    assert ("attempt-N.asm", "not yet") not in [(n, s) for n, s, _ in file_rows(tmp_path)]


def test_the_draft_rows_list_the_files_of_the_drafts_folder(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from barthelona.ui.run_info import draft_rows

    (tmp_path / "attempt-2.asm").write_text("bb", encoding="utf-8")
    (tmp_path / "attempt-1.asm").write_text("a", encoding="utf-8")
    (tmp_path / "subfolder").mkdir()

    rows = draft_rows(tmp_path)

    assert [name for name, _ in rows] == ["attempt-1.asm", "attempt-2.asm"]
    assert rows[0][1].startswith("1 bytes")


def test_a_missing_drafts_folder_gives_no_rows(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from barthelona.ui.run_info import draft_rows

    assert draft_rows(tmp_path / "nowhere") == []


def test_the_activity_line_says_how_long_ago_the_run_last_did_anything() -> None:
    from datetime import UTC, datetime, timedelta

    from barthelona.domain import EventKind, RunEvent
    from barthelona.ui.run_info import activity_line

    now = datetime.now(UTC)
    event = RunEvent(
        run_id="r1", seq=0, ts=now - timedelta(seconds=90), kind=EventKind.LLM_CALL, payload={"status": "x"}
    )

    assert "90 s ago" in activity_line(event, now)
    assert "No activity" in activity_line(None, now)
