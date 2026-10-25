"""When a run last did anything, in words, so a long model call is not mistaken for a freeze."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from barthelona.domain.layout import REASONING_FILE

# A remote lane answers in about two minutes, but when it times out the chain falls through to the local
# model, whose calls took 485 s on average and 980 s at worst (measured 2026-10-25). A shorter threshold
# called those runs frozen while they were working.
STALE_AFTER_S = 1200


def ago(seconds: float) -> str:
    """'42 s ago', '3 min ago', '1 h 5 min ago'."""
    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole} s ago"
    minutes = whole // 60
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h {minutes % 60} min ago"


def last_activity(run_folder: Path, last_event: datetime | None) -> datetime | None:
    """The newest sign of life of a run: its last event, or a model reply written to its reasoning log."""
    seen = [last_event] if last_event is not None else []
    log = run_folder / REASONING_FILE
    if log.is_file():
        seen.append(datetime.fromtimestamp(log.stat().st_mtime, UTC))
    return max(seen, default=None)


def activity_text(last: datetime | None, now: datetime) -> tuple[str, bool]:
    """(sentence, stale): when the run last did anything, and whether that was too long ago to be normal."""
    if last is None:
        return "No activity yet.", False
    seconds = (now - last).total_seconds()
    clock = last.astimezone().strftime("%H:%M:%S")
    return f"Last activity: {ago(seconds)} (at {clock}).", seconds > STALE_AFTER_S
