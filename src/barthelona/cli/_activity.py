"""The agent-activity log every model-calling command writes by default (hackathon requirement)."""

from __future__ import annotations

from barthelona.llm.trace import ReasoningLog

DEFAULT_ACTIVITY_LOG = "var/activity.md"
OFF = "off"

ACTIVITY_HELP = (
    "Append every model's reasoning and answer to this file ('-' prints to stderr, 'off' disables). "
    f"Default: {DEFAULT_ACTIVITY_LOG}. The log holds the request text; var/ is not in git."
)


def activity_log(target: str) -> ReasoningLog | None:
    """The log for *target*, or ``None`` when it is switched off."""
    if not target or target.lower() == OFF:
        return None
    return ReasoningLog(target)
