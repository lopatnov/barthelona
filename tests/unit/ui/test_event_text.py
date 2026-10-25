"""Run events as readable sentences."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from barthelona.domain import EventKind, RunEvent
from barthelona.ui.event_text import describe


def _event(event_kind: EventKind, node_id: str | None = None, **payload: Any) -> RunEvent:
    return RunEvent(
        run_id="r1", seq=0, ts=datetime.now(UTC), kind=event_kind, node_id=node_id, payload=payload
    )


@pytest.mark.parametrize(
    ("node", "words"),
    [("intake", "Understood the request"), ("spec", "specification"), ("codegen", "emulator")],
)
def test_a_finished_step_is_named_in_plain_words(node: str, words: str) -> None:
    assert words in describe(_event(EventKind.NODE_END, node))


def test_an_unknown_step_still_says_which_one() -> None:
    assert describe(_event(EventKind.NODE_END, "mystery")) == "Finished step mystery"


def test_a_gate_request_tells_the_person_what_to_do() -> None:
    text = describe(_event(EventKind.GATE_REQUESTED, gate_id="run-1-G1", kind="G1"))

    assert "Waiting for you" in text and "specification and the tests" in text and "Approvals" in text


@pytest.mark.parametrize(("decision", "word"), [("approve", "approved"), ("reject", "rejected")])
def test_a_gate_decision_says_what_the_person_chose(decision: str, word: str) -> None:
    text = describe(_event(EventKind.GATE_RESOLVED, gate_id="run-1-G4", decision=decision))

    assert word in text and "finished code" in text


@pytest.mark.parametrize(
    ("reason", "words"),
    [
        ("green", "Done"),
        ("max_attempts", "attempts"),
        ("no_model_available", "429"),
        ("weird", "Stopped: weird"),
    ],
)
def test_a_stop_reason_is_explained(reason: str, words: str) -> None:
    assert words in describe(_event(EventKind.STOP, stop_reason=reason))


def test_an_error_shows_its_message() -> None:
    assert describe(_event(EventKind.ERROR, message="disk full")) == "Problem: disk full"


def test_an_unknown_kind_falls_back_to_its_name_and_payload_keys() -> None:
    assert describe(_event(EventKind.BUDGET, tokens=5)) == "Budget (tokens)"
