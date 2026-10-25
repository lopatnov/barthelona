"""The console trace, the combined trace and the Live Run panel's entry parser."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from barthelona.domain import LLMCallRecord
from barthelona.llm.trace import ConsoleTrace, ReasoningLog, TraceAll, _entry
from barthelona.llm.types import Completion
from barthelona.ui.reasoning_panel import all_entries


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


def test_every_entry_of_the_log_is_listed_oldest_first() -> None:
    log = (
        "## a via m (1 in)\n\n### reasoning\n\nx\n\n### answer\n\nfirst\n\n"
        "## b via m (2 in)\n\n### answer\n\nsecond\n\n"
        "## c via m (3 in)\n\n### answer\n\nthird\n\n"
    )

    entries = all_entries(log)

    assert [entry.splitlines()[0] for entry in entries] == [
        "## a via m (1 in)",
        "## b via m (2 in)",
        "## c via m (3 in)",
    ]


def test_a_markdown_heading_inside_an_answer_does_not_split_an_entry() -> None:
    log = "## a via m (1 in)\n\n### answer\n\n## Title of a README\n\ntext\n\n"

    assert len(all_entries(log)) == 1


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


def test_an_entry_is_split_into_prompt_thinking_and_answer() -> None:
    from barthelona.ui.reasoning_panel import split_entry

    body = "### prompt\n\n[user]\nhi\n\nmore\n\n### reasoning\n\nwhy\n\n### answer\n\nok"

    assert split_entry(body) == {"prompt": "[user]\nhi\n\nmore", "reasoning": "why", "answer": "ok"}


def test_an_older_entry_without_a_prompt_still_splits() -> None:
    from barthelona.ui.reasoning_panel import split_entry

    assert split_entry("### reasoning\n\nwhy\n\n### answer\n\nok") == {"reasoning": "why", "answer": "ok"}


def test_an_entry_that_is_not_in_the_log_format_is_shown_whole_not_a_crash() -> None:
    from barthelona.ui.reasoning_panel import split_entry

    assert split_entry("text without markers") == {"answer": "text without markers"}


def test_a_heading_that_names_the_answering_model_starts_an_entry() -> None:
    log = "## worker via meterless_auto -> nvidia/some-model (1 in, 2 out, 1.0s)\n\n### answer\n\nok\n\n"

    assert len(all_entries(log)) == 1


def test_console_progress_prints_a_timestamped_line(capsys: pytest.CaptureFixture[str]) -> None:
    from barthelona.llm.trace import ConsoleProgress

    ConsoleProgress()("asking m, waiting for its reply")

    assert re.match(r"\[\d\d:\d\d:\d\d\] asking m, waiting for its reply\n", capsys.readouterr().err)


def test_an_entry_says_which_models_failed_first_and_why() -> None:
    notes = ("meterless_deep: Too Many Requests after 2.3s [server]", "meterless_auto: disabled")
    done = _done().model_copy(update={"fallbacks": notes, "prompt": "[user]\nhi"})

    entry = _entry("worker", done)

    assert "### tried first\n\n- " + notes[0] + "\n- " + notes[1] in entry
    assert entry.index("### tried first") < entry.index("### prompt")


def test_an_entry_that_needed_no_fallback_has_no_tried_first_part() -> None:
    assert "### tried first" not in _entry("worker", _done())


def test_the_panel_splits_the_tried_first_part_off() -> None:
    from barthelona.ui.reasoning_panel import split_entry

    body = (
        "### tried first\n\n- meterless_deep: 429\n\n### prompt\n\n[user]\nhi\n\n"
        "### reasoning\n\nwhy\n\n### answer\n\nok"
    )

    assert split_entry(body) == {
        "tried first": "- meterless_deep: 429",
        "prompt": "[user]\nhi",
        "reasoning": "why",
        "answer": "ok",
    }
