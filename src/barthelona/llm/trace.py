"""The optional reasoning log: what each model thought and answered, for people watching a run."""

from __future__ import annotations

import sys
from pathlib import Path

from barthelona.llm.types import Completion

STDERR = "-"


class ReasoningLog:
    """Appends one markdown entry per answered request to a file, or prints it to stderr for ``-``.

    The log holds the models' answers and thoughts verbatim, so it can hold task text and anything the model
    repeated from its prompt: keep it out of git and do not share it. Prompts never contain keys
    (invariant 10), so nothing is redacted.
    """

    def __init__(self, target: str | Path) -> None:
        self._target = str(target)

    def __call__(self, role: str, done: Completion) -> None:
        record = done.record
        seconds = record.latency_ms / 1000
        thought = done.reasoning or "(the model sent no reasoning)"
        usage = f"{record.tokens_in} in, {record.tokens_out} out, {seconds:.1f}s, stop={record.stop_reason}"
        entry = f"## {role} via {done.served_by} ({usage})\n\n### reasoning\n\n{thought}\n\n"
        entry += f"### answer\n\n{done.text}\n\n"
        if self._target == STDERR:
            sys.stderr.write(entry)
            return
        path = Path(self._target)
        path.parent.mkdir(parents=True, exist_ok=True)
        owner_only = 0o600  # the log holds the request text; Windows ignores the mode
        path.touch(mode=owner_only, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(entry)
