"""The agent-activity log is on by default for the commands that call models."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.cli._activity import DEFAULT_ACTIVITY_LOG, activity_log
from barthelona.llm.trace import ReasoningLog


def test_the_default_target_is_a_log_under_var() -> None:
    assert DEFAULT_ACTIVITY_LOG == "var/activity.md"
    assert isinstance(activity_log(DEFAULT_ACTIVITY_LOG), ReasoningLog)


@pytest.mark.parametrize("target", ["off", "OFF", ""])
def test_off_or_empty_switches_the_log_off(target: str) -> None:
    assert activity_log(target) is None


def test_stderr_and_a_file_are_accepted(tmp_path: Path) -> None:
    assert isinstance(activity_log("-"), ReasoningLog)
    assert isinstance(activity_log(str(tmp_path / "log.md")), ReasoningLog)


def test_the_console_shows_the_reasoning_unless_told_not_to(tmp_path: Path) -> None:
    target = str(tmp_path / "log.md")
    default = activity_log(target)
    assert default is not None
    assert default._echo is True
    quiet = activity_log(target, show=False)
    assert quiet is not None
    assert quiet._echo is False
