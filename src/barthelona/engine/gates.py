"""What a human sees at a gate, and what an event says about a finished node, kept small and readable.

A gate payload is capped (`MAX_PAYLOAD_BYTES`, F-20): bulky data belongs in the run folder. The full spec and
tests are in `spec.json` and `tests.json` there; the gate carries what a person needs to decide.
"""

from __future__ import annotations

import json
from typing import Any

PAYLOAD_BUDGET = 12_000  # bytes of JSON, under the store's limit with room for the gate's own fields
_BRIEF_SPEC_KEYS = ("slug", "request_lang", "target", "summary_en", "requirements", "modules", "constraints")
_TEST_KEYS = ("id", "kind", "symbol", "level", "inputs", "expect")
_SUMMARY_KEYS = ("stop", "verdict", "g1", "g4")
_TEXT_LIMIT = 120


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def g1_payload(spec: dict[str, Any], tests: list[dict[str, Any]]) -> dict[str, Any]:
    """The spec and the tests for the G1 approval, cut down until they fit one gate."""
    lines = [{key: test[key] for key in _TEST_KEYS if key in test} for test in tests]
    payload: dict[str, Any] = {"project_spec": spec, "tests": lines}
    if _size(payload) <= PAYLOAD_BUDGET:
        return payload
    brief = {key: spec[key] for key in _BRIEF_SPEC_KEYS if key in spec}
    payload = {
        "project_spec": brief | {"note": "the full spec is spec.json in the run folder"},
        "tests": lines,
    }
    _fit(payload, len(lines))
    return payload


def _fit(payload: dict[str, Any], total_tests: int) -> None:
    """Drop tests, then shorten requirement texts, then drop requirements, until the payload fits."""
    tests: list[Any] = payload["tests"]
    while _size(payload) > PAYLOAD_BUDGET and tests:
        tests.pop()
        payload["tests_shown"], payload["tests_total"] = len(tests), total_tests
    requirements: list[dict[str, Any]] = payload["project_spec"].get("requirements", [])
    if _size(payload) > PAYLOAD_BUDGET:
        for requirement in requirements:
            requirement["text"] = _shorten(str(requirement.get("text", "")))
    while _size(payload) > PAYLOAD_BUDGET and requirements:
        requirements.pop()
        payload["project_spec"]["requirements_shown"] = len(requirements)


def _shorten(text: str) -> str:
    return text if len(text) <= _TEXT_LIMIT else text[: _TEXT_LIMIT - 3] + "..."


def g4_payload(source_file: str, verdict: str | None) -> dict[str, Any]:
    """The final approval: where the source is and what the oracle said about it."""
    return {"source_file": source_file, "verdict": verdict or "unknown"}


def node_summary(update: dict[str, Any] | None) -> dict[str, Any]:
    """One short line of data for a node's `node_end` event, from the state update it returned."""
    summary: dict[str, Any] = {}
    for key, value in (update or {}).items():
        if key in _SUMMARY_KEYS:
            summary[key] = value
        elif key == "spec" and isinstance(value, dict):
            summary["requirements"] = len(value.get("requirements", []))
        elif key == "tests" and isinstance(value, list):
            summary["tests"] = len(value)
        elif key == "facts" and isinstance(value, str):
            summary["facts_chars"] = len(value)
    return summary
