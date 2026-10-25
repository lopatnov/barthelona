"""The reasoning log: what each model was asked, thought and answered, for people watching a run."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from barthelona.llm.types import Completion

STDERR = "-"
CONSOLE_REASONING_CHARS = 1500  # the console shows the start of long thoughts and answers; the files hold all
CONSOLE_ANSWER_CHARS = 500
CONSOLE_PROMPT_CHARS = 800
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


def _shortened(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]} ... ({len(text) - limit} more characters)"


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


class ConsoleTrace:
    """Prints each answered request to stderr, long thoughts and answers cut short: a live worker window."""

    def __call__(self, role: str, done: Completion) -> None:
        thought = _shortened(done.reasoning or "(the model sent no reasoning)", CONSOLE_REASONING_CHARS)
        answer = _shortened(done.text, CONSOLE_ANSWER_CHARS)
        asked = f"prompt: {_shortened(done.prompt, CONSOLE_PROMPT_CHARS)}\n" if done.prompt else ""
        text = f"\n{_heading(role, done)}\n{asked}thinking: {thought}\nanswer: {answer}\n"
        encoding = sys.stderr.encoding or "utf-8"  # a legacy console codepage must not crash a run
        sys.stderr.write(text.encode(encoding, "replace").decode(encoding))
        sys.stderr.flush()


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
