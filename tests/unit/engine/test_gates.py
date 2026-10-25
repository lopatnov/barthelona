"""Gate payloads stay readable and under the store's size limit."""

from __future__ import annotations

import json

from barthelona.engine.gates import PAYLOAD_BUDGET, g1_payload, g4_payload, node_summary
from barthelona.persistence import MAX_PAYLOAD_BYTES


def _spec(requirements: int) -> dict[str, object]:
    return {
        "slug": "quiz",
        "summary_en": "A quiz.",
        "requirements": [{"id": f"R{n}", "text": "x" * 200} for n in range(requirements)],
        "modules": [{"path": "src/quiz.asm"}],
        "request_original": "y" * 5000,
    }


def _tests(count: int) -> list[dict[str, object]]:
    return [
        {"id": f"T{n}", "kind": "run", "inputs": {"stdin": "a" * 100}, "origin": "model"}
        for n in range(count)
    ]


def test_a_small_spec_goes_whole_and_each_test_is_one_short_line() -> None:
    payload = g1_payload(_spec(2), _tests(2))
    assert payload["project_spec"]["request_original"] == "y" * 5000
    assert payload["tests"][0] == {"id": "T0", "kind": "run", "inputs": {"stdin": "a" * 100}}


def test_a_big_spec_is_cut_to_fit_one_gate() -> None:
    payload = g1_payload(_spec(60), _tests(200))
    assert len(json.dumps(payload).encode()) <= PAYLOAD_BUDGET < MAX_PAYLOAD_BYTES
    assert "request_original" not in payload["project_spec"]
    assert len(payload["project_spec"]["requirements"][0]["text"]) <= 120
    assert payload["tests_total"] == 200
    assert payload["tests_shown"] == len(payload["tests"]) < 200


def test_the_final_gate_names_the_file_and_the_oracle_verdict() -> None:
    assert g4_payload("main.asm", "pass") == {"source_file": "main.asm", "verdict": "pass"}
    assert g4_payload("main.asm", None)["verdict"] == "unknown"


def test_a_node_summary_counts_and_never_copies_text() -> None:
    update = {"spec": _spec(3), "tests": _tests(4), "verdict": "pass", "facts": "abc"}
    assert node_summary(update) == {"requirements": 3, "tests": 4, "verdict": "pass", "facts_chars": 3}
    assert node_summary(None) == {}
