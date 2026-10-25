"""The console trace, the combined trace and the Live Run panel's entry parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.domain import LLMCallRecord
from barthelona.llm.trace import ConsoleTrace, ReasoningLog, TraceAll, _entry
from barthelona.llm.types import Completion
from barthelona.ui.reasoning_panel import latest_entries


def _done(text: str = "answer text", reasoning: str = "thought text") -> Completion:
    record = LLMCallRecord(
        provider="meterless",
        model="meterless/auto",
        prompt_hash="0" * 64,
        tokens_in=10,
        tokens_out=20,
        latency_ms=1500,
        stop_reason="stop",
    )
    return Completion(
        text=text,
        reasoning=reasoning,
        record=record,
        served_by="meterless_auto",
    )


def test_the_log_file_gets_one_entry_per_answer(tmp_path: Path) -> None:
    log = ReasoningLog(tmp_path / "run" / "reasoning.md")

    log("worker", _done())
    log("planner", _done("second"))

    text = (tmp_path / "run" / "reasoning.md").read_text(encoding="utf-8")
    assert text.count("via meterless_auto") == 2
    assert "## worker via meterless_auto (10 in, 20 out, 1.5s, stop=stop)" in text
    assert "thought text" in text


def test_the_console_trace_prints_the_whole_prompt_thinking_and_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ConsoleTrace()("worker", _done("x" * 5000, "y" * 5000).model_copy(update={"prompt": "p" * 5000}))

    shown = capsys.readouterr().err
    assert "worker via meterless_auto" in shown
    assert "p" * 5000 in shown and "y" * 5000 in shown and "x" * 5000 in shown
    assert "more characters" not in shown


def test_trace_all_calls_every_trace_and_skips_none(tmp_path: Path) -> None:
    first, second = tmp_path / "a.md", tmp_path / "b.md"

    TraceAll(ReasoningLog(first), None, ReasoningLog(second))("worker", _done())

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8") != ""


def test_the_panel_lists_the_newest_entries_first() -> None:
    log = (
        "## a via m (1 in)\n\n### reasoning\n\nx\n\n### answer\n\nfirst\n\n"
        "## b via m (2 in)\n\n### answer\n\nsecond\n\n"
        "## c via m (3 in)\n\n### answer\n\nthird\n\n"
    )

    entries = latest_entries(log, limit=2)

    assert [entry.splitlines()[0] for entry in entries] == ["## c via m (3 in)", "## b via m (2 in)"]


def test_a_markdown_heading_inside_an_answer_does_not_split_an_entry() -> None:
    log = "## a via m (1 in)\n\n### answer\n\n## Title of a README\n\ntext\n\n"

    assert len(latest_entries(log)) == 1


def test_a_trace_that_fails_does_not_stop_the_others(tmp_path: Path) -> None:
    blocked = tmp_path / "is-a-file"
    blocked.write_text("x", encoding="utf-8")
    good = tmp_path / "good.md"

    with pytest.raises(OSError):
        TraceAll(ReasoningLog(blocked / "log.md"), ReasoningLog(good))("worker", _done())

    assert "thought text" in good.read_text(encoding="utf-8")


def test_the_heading_names_the_model_a_router_picked() -> None:
    done = _done().model_copy(update={"answered_by": "nvidia/nemotron-x"})

    assert "worker via meterless_auto -> nvidia/nemotron-x (10 in" in _entry("worker", done)


def test_the_panel_splits_the_prompt_from_the_rest_of_an_entry() -> None:
    from barthelona.ui.reasoning_panel import split_prompt

    body = "### prompt\n\n[user]\nhi\n\nmore\n\n### reasoning\n\nt\n\n### answer\n\na"
    assert split_prompt(body) == ("[user]\nhi\n\nmore", "### reasoning\n\nt\n\n### answer\n\na")
    assert split_prompt("### reasoning\n\nt") == ("", "### reasoning\n\nt")
