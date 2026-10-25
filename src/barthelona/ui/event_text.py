"""Run events as sentences a person can read; the raw ids and JSON stay in the database."""

from __future__ import annotations

from barthelona.domain import EventKind, RunEvent

_NODES = {
    "preflight": "Checked that the run can start",
    "intake": "Understood the request (language, goal, assumptions)",
    "spec": "Wrote the specification (requirements and modules)",
    "test_author": "Wrote the acceptance tests",
    "validate_spec": "Checked the specification against the tests",
    "g1_gate": "Your decision on the specification and tests is in",
    "codegen": "Wrote the program; the assembler and the emulator checked it",
    "g4_gate": "Your decision on the finished code is in",
    "finalize": "Run finished",
}

GATES = {"G1": "the specification and the tests", "G4": "the finished code"}

STOPS = {
    "green": "Done: the program assembles and passes all its tests",
    "max_attempts": "Stopped: the models did not produce a valid result within the allowed attempts",
    "no_model_available": "Stopped: no model answered (provider down or rate-limited, for example HTTP 429)",
    "budget_tokens": "Stopped: the token limit was reached",
    "budget_time": "Stopped: the time limit was reached",
    "budget_cost": "Stopped: the money cap was reached",
    "max_sprints": "Stopped: the sprint limit was reached",
    "human_abort": "Stopped by you",
    "unsupported_target": "Stopped: this target is not supported yet",
    "refusal": "Stopped: a model refused the request",
    "infra_error": "Stopped: a tool the run needs was unavailable (for example the assembler)",
}


def _gate_name(gate_id: str, fallback_kind: str = "") -> str:
    """'the specification and the tests' for ``<run>-G1``; the gate id's last part is its kind."""
    kind = fallback_kind or gate_id.rsplit("-", 1)[-1]
    return GATES.get(kind, f"gate {kind}")


def stop_text(reason: str, detail: str = "") -> str:
    """The sentence for a stop reason, with the step's own words for it when the event carries them."""
    sentence = STOPS.get(reason, f"Stopped: {reason or 'no reason given'}")
    return f"{sentence} ({detail})" if detail else sentence


def describe(event: RunEvent) -> str:
    """One plain sentence for *event*; unknown kinds fall back to the kind name and the payload keys."""
    payload = event.payload
    match event.kind:
        case EventKind.NODE_END:
            return _NODES.get(event.node_id or "", f"Finished step {event.node_id}")
        case EventKind.GATE_REQUESTED:
            what = _gate_name(str(payload.get("gate_id", "")), str(payload.get("kind", "")))
            return f"Waiting for you: approve or reject {what} on the Approvals page"
        case EventKind.GATE_RESOLVED:
            what = _gate_name(str(payload.get("gate_id", "")))
            verdict = "approved" if payload.get("decision") == "approve" else "rejected"
            return f"You {verdict} {what}"
        case EventKind.STOP:
            reason = str(payload.get("stop_reason", ""))
            return stop_text(reason, str(payload.get("detail", "")))
        case EventKind.ERROR:
            detail = payload.get("message") or payload.get("error") or payload.get("ignored_command") or ""
            return f"Problem: {detail}" if detail else "Problem (see the run's event details)"
        case EventKind.LLM_CALL if payload.get("status"):
            return f"Model request: {payload['status']}"
        case EventKind.PHASE if payload.get("packaged"):
            return f"Wrote the project ({payload.get('files')} files) into {payload['packaged']}"
        case EventKind.PHASE if payload.get("recovered"):
            return "The worker restarted and picked this run up again"
    keys = ", ".join(payload) or "no details"
    return f"{event.kind.value.replace('_', ' ').capitalize()} ({keys})"
