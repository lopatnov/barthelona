"""The reasoning log: what each model was asked, thought and answered, for people watching a run."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from barthelona.llm.types import Completion

STDERR = "-"
PROMPT_HEADING = "### prompt"

Trace = Callable[[str, Completion], None]


def _heading(role: str, done: Completion) -> str:
    record = done.record
    seconds = record.latency_ms / 1000
    usage = f"{record.tokens_in} in, {record.tokens_out} out, {seconds:.1f}s, stop={record.stop_reason}"
    model = f" -> {done.answered_by}" if done.answered_by else ""  # the model a router picked, if it says
    return f"## {role} via {done.served_by}{model} ({usage})"


def _entry(role: str, done: Completion) -> str:
    thought = done.reasoning or "(the model sent no reasoning)"
    asked = f"{PROMPT_HEADING}\n\n{done.prompt}\n\n" if done.prompt else ""
    return f"{_heading(role, done)}\n\n{asked}### reasoning\n\n{thought}\n\n### answer\n\n{done.text}\n\n"


class ReasoningLog:
    """Appends one markdown entry per answered request to a file, or prints it to stderr for ``-``.

    The log holds the prompts, the models' answers and thoughts verbatim, so it holds task text and anything
    the model repeated from its prompt: keep it out of git and do not share it. Prompts never contain keys
    (invariant 10), so nothing is redacted.
    """

    def __init__(self, target: str | Path) -> None:
        self._target = str(target)

    def __call__(self, role: str, done: Completion) -> None:
        entry = _entry(role, done)
        if self._target == STDERR:
            sys.stderr.write(entry)
            return
        path = Path(self._target)
        path.parent.mkdir(parents=True, exist_ok=True)
        owner_only = 0o600  # the log holds the request text; Windows ignores the mode
        path.touch(mode=owner_only, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(entry)


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")  # the worker window's local time


def _to_stderr(text: str) -> None:
    encoding = sys.stderr.encoding or "utf-8"  # a legacy console codepage must not crash a run
    sys.stderr.write(text.encode(encoding, "replace").decode(encoding))
    sys.stderr.flush()


class ConsoleProgress:
    """Prints one timestamped line when a model request goes out, is repeated or fails over."""

    def __call__(self, message: str) -> None:
        _to_stderr(f"[{_stamp()}] {message}\n")


class ConsoleTrace:
    """Prints each answered request to stderr in full (prompt, thinking, answer): a live worker window."""

    def __call__(self, role: str, done: Completion) -> None:
        thought = done.reasoning or "(the model sent no reasoning)"
        asked = f"prompt: {done.prompt}\n" if done.prompt else ""
        _to_stderr(
            f"\n[{_stamp()}] {_heading(role, done)}\n{asked}thinking: {thought}\nanswer: {done.text}\n"
        )


class TraceAll:
    """Calls several traces for one answered request; ``None`` entries are skipped."""

    def __init__(self, *traces: Trace | None) -> None:
        self._traces = [trace for trace in traces if trace is not None]

    def __call__(self, role: str, done: Completion) -> None:
        """Every trace gets the reply; the first file error is raised after, so a bad file costs no other."""
        first_error: OSError | None = None
        for trace in self._traces:
            try:
                trace(role, done)
            except OSError as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
