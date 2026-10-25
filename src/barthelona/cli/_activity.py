"""The agent-activity log every model-calling command writes by default (hackathon requirement)."""

from __future__ import annotations

from barthelona.llm.trace import ReasoningLog

DEFAULT_ACTIVITY_LOG = "var/activity.md"
OFF = "off"

ACTIVITY_HELP = (
    "Append every model's reasoning and answer to this file ('-' prints to stderr, 'off' disables). "
    f"Default: {DEFAULT_ACTIVITY_LOG}. The log holds the request text; var/ is not in git."
)


SHOW_HELP = "Also print every model's reasoning and answer to the console (on by default)."


def activity_log(target: str, *, show: bool = True) -> ReasoningLog | None:
    """The log for *target*, echoed to the console unless *show* is off; ``None`` when it is switched off."""
    if not target or target.lower() == OFF:
        return None
    return ReasoningLog(target, echo=show)
