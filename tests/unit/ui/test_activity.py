"""When a run last did anything, and why a queued run waits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.domain import EventKind, Profile, Run, RunBudget, RunEvent, RunMode, RunStatus
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store
from barthelona.ui.activity import STALE_AFTER_S, activity_text, ago, last_activity
from barthelona.ui.event_text import describe, stop_text
from barthelona.ui.reasoning_panel import all_entries
from barthelona.ui.run_info import queued_text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (5, "5 s ago"),
        (59, "59 s ago"),
        (60, "1 min ago"),
        (3 * 60 + 20, "3 min ago"),
        (3900, "1 h 5 min ago"),
    ],
)
def test_ago_speaks_in_seconds_minutes_and_hours(seconds: int, text: str) -> None:
    assert ago(seconds) == text


def test_a_run_with_no_sign_of_life_says_so() -> None:
    assert activity_text(None, datetime.now(UTC)) == ("No activity yet.", False)


def test_silence_longer_than_a_model_call_is_stale() -> None:
    now = datetime.now(UTC)
    long_call = STALE_AFTER_S + 60  # a local fallback call runs for minutes, so the threshold is generous

    fresh, fresh_flag = activity_text(now - timedelta(seconds=90), now)
    stale, stale_flag = activity_text(now - timedelta(seconds=long_call), now)

    assert "1 min ago" in fresh and not fresh_flag
    assert ago(long_call) in stale and stale_flag


def test_the_newest_of_the_last_event_and_the_reasoning_log_counts(tmp_path: Path) -> None:
    old = datetime.now(UTC) - timedelta(hours=1)
    (tmp_path / "reasoning.md").write_text("## x via y (1 in)\n", encoding="utf-8")

    newest = last_activity(tmp_path, old)

    assert newest is not None and newest > old
    assert last_activity(tmp_path / "nowhere", old) == old
    assert last_activity(tmp_path / "nowhere", None) is None


def _run(run_id: str, status: RunStatus = RunStatus.QUEUED) -> Run:
    return Run(
        id=run_id,
        mode=RunMode.CREATE,
        workspace=f"demos/{run_id}",
        target=builtin_presets()[0],
        profile=Profile.METERLESS,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=400000, max_sprints=10, cloud_allowed=True),
        status=status,
    )


def test_a_queued_run_names_the_run_the_worker_is_busy_with() -> None:
    text = queued_text(_run("run-b"), [_run("run-a", RunStatus.RUNNING)])

    assert (
        "Queued behind `run-a`" in text
        and "demos/run-a" in text
        and "Cancel Run" in text
        and "Resume" in text
    )


def test_a_queued_run_with_nothing_running_points_at_the_worker() -> None:
    assert "worker" in queued_text(_run("run-b"), [])


def test_a_stop_says_what_the_step_that_stopped_the_run_said() -> None:
    event = RunEvent(
        run_id="run-a",
        seq=0,
        ts=datetime.now(UTC),
        kind=EventKind.STOP,
        payload={"stop_reason": "max_attempts", "detail": "worker gave no valid TestsDraft: no JSON object"},
    )

    assert describe(event).endswith("(worker gave no valid TestsDraft: no JSON object)")
    assert stop_text("max_attempts", "") == stop_text(
        "max_attempts"
    )  # a run that said nothing reads as before


def test_a_heading_with_a_time_starts_an_entry_too() -> None:
    log = "## 14:09:25 worker via meterless_auto -> m (1 in, 2 out, 1.0s, stop=stop)\n\n### answer\n\nok\n\n"

    assert len(all_entries(log)) == 1


def _page() -> None:
    from barthelona.ui.pages.live_run import page_live_run

    page_live_run()


def test_a_running_run_with_no_recent_activity_gets_the_stale_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "var" / "runs" / "run-a").mkdir(parents=True)
    store = open_store(tmp_path / "var" / "app.sqlite")
    store.create_run(_run("run-a"))
    store.set_run_status("run-a", RunStatus.RUNNING)
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    store.append_events(
        [RunEvent(run_id="run-a", seq=0, ts=long_ago, kind=EventKind.NODE_END, node_id="intake")]
    )
    store.close()
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    warnings = " ".join(box.value for box in app.warning)
    assert not app.exception and "Last activity: 1 h" in warnings and "worker window" in warnings
