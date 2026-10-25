"""Live Run renders a run's status, parameters and plain-language events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from barthelona.domain import (
    EventKind,
    GateRequest,
    Profile,
    Run,
    RunBudget,
    RunEvent,
    RunMode,
    RunStatus,
)
from barthelona.domain.presets import builtin_presets
from barthelona.persistence import open_store


def _page() -> None:
    from barthelona.ui.pages.live_run import page_live_run

    page_live_run()


def _run_waiting_for_g1(root: Path) -> Run:
    (root / "var" / "runs" / "run-1").mkdir(parents=True)
    (root / "var" / "runs" / "run-1" / "request.txt").write_text("Print hello.", encoding="utf-8")
    run = Run(
        id="run-1",
        mode=RunMode.CREATE,
        workspace="demos/hello-demo",
        target=builtin_presets()[0],
        profile=Profile.METERLESS,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=400000, max_sprints=10, cloud_allowed=True),
    )
    store = open_store(root / "var" / "app.sqlite")
    store.create_run(run)
    store.append_events(
        [
            RunEvent(run_id="run-1", seq=0, ts=datetime.now(UTC), kind=EventKind.NODE_END, node_id="intake"),
        ]
    )
    store.open_gate(
        GateRequest(gate_id="run-1-G1", kind="G1", run_id="run-1", options=["approve", "reject"], payload={})
    )
    store.set_run_status("run-1", RunStatus.WAITING_GATE)
    store.close()
    return run


def test_a_run_waiting_at_g1_says_what_it_waits_for_and_shows_its_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_waiting_for_g1(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not app.exception
    warnings = " ".join(box.value for box in app.warning)
    assert "Waiting for your approval: G1" in warnings and "specification and the tests" in warnings
    text = " ".join(item.value for item in [*app.markdown, *app.code])
    assert "demos/hello-demo" in text and "Print hello." in text and "meterless" in text
    assert any("Understood the request" in item.value for item in app.markdown)


def test_live_run_opens_on_the_run_that_was_just_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _run_waiting_for_g1(tmp_path)
    store = open_store(tmp_path / "var" / "app.sqlite")
    store.create_run(first.model_copy(update={"id": "run-2", "status": RunStatus.QUEUED}))
    store.close()
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False
    app.session_state["active_run_id"] = "run-1"

    app.run()

    assert app.selectbox[0].value == "run-1"  # not run-2, the newest


def test_the_event_log_comes_before_the_reasoning_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_waiting_for_g1(tmp_path)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    titles = [item.value for item in app.subheader]
    assert titles.index("📜 What happened") < titles.index("🧠 Model reasoning")


def test_the_reasoning_panel_shows_what_was_asked_the_thinking_and_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_waiting_for_g1(tmp_path)
    entry = (
        "## worker via meterless_auto -> some-model (1 in, 2 out, 1.0s, stop=stop)\n\n"
        "### prompt\n\n[user]\nWrite hello.\n\n### reasoning\n\nthinking text\n\n"
        "### answer\n\nhello code\n\n"
    )
    log = tmp_path / "var" / "runs" / "run-1" / "reasoning.md"
    log.write_text(entry, encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not app.exception and not app.error
    assert [tab.label for tab in app.tabs] == ["Asked", "Thinking", "Answer"]
    shown = " ".join(block.value for block in app.code)
    assert "Write hello." in shown and "thinking text" in shown and "hello code" in shown


def test_a_log_entry_in_the_wrong_format_does_not_break_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_waiting_for_g1(tmp_path)
    log = tmp_path / "var" / "runs" / "run-1" / "reasoning.md"
    log.write_text("## w via r (1 in)\n\nno section markers at all\n", encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not app.exception and not app.error


def test_the_panel_shows_a_long_prompt_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run_waiting_for_g1(tmp_path)
    prompt = "[user]\n" + "line of the spec\n" * 2000 + "THE END OF THE PROMPT"
    entry = (
        "## worker via meterless_auto (1 in, 2 out, 1.0s, stop=stop)\n\n"
        f"### prompt\n\n{prompt}\n\n### reasoning\n\nwhy\n\n### answer\n\nok\n\n"
    )
    log = tmp_path / "var" / "runs" / "run-1" / "reasoning.md"
    log.write_text(entry, encoding="utf-8", newline="\n")
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_function(_page, default_timeout=30)
    app.session_state["auto_poll"] = False

    app.run()

    assert not app.exception and not app.error
    assert any(block.value.endswith("THE END OF THE PROMPT") for block in app.code)
