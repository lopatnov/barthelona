"""The worker's host-side services: where requests and specs live on disk, and the store behind the nodes.

A run's files sit in `runs/<run_id>/` (docs/architecture.md §18): the UI writes `request.txt` when it queues
the run, the engine writes `spec.json` and `tests.json` for gate G1.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import orjson

from barthelona.domain import (
    EventKind,
    ProjectSpec,
    Run,
    RunEvent,
    TestCase,
)
from barthelona.engine.graph import Services
from barthelona.engine.preflight import preflight_for
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.zetaris import ZetarisConfig, ZetarisError, facts_block, run_sql
from barthelona.persistence import Store

REQUEST_FILE = "request.txt"
SPEC_FILE = "spec.json"
TESTS_FILE = "tests.json"


def run_dir(runs_dir: Path, run_id: str) -> Path:
    return runs_dir / run_id


DEFAULT_FACTS_SQL = (
    "SELECT number, name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls"
    " UNION ALL SELECT topic, fact, '', '', '' FROM barthelona_files.abi_facts"
)


def no_facts() -> str:
    return ""


def default_facts(
    emit_event: Callable[[str, str], None] | None = None,
) -> Callable[[], str]:
    """Knowledge-table facts when ZETARIS_API_KEY is set, none otherwise; a down Zetaris never stops a run.

    If emit_event is provided, it will be called with (run_id, error_message) when Zetaris fails.
    """
    config = ZetarisConfig.from_env(os.environ)
    if config is None:
        return no_facts

    def facts(run_id: str | None = None) -> str:
        try:
            return facts_block(run_sql(config, DEFAULT_FACTS_SQL, 100), DEFAULT_FACTS_SQL)
        except ZetarisError as e:
            if emit_event and run_id:
                emit_event(run_id, f"Zetaris facts unavailable: {e}")
            return ""

    return facts


def zetaris_facts(sql: str) -> Callable[[], str]:
    """A facts source that runs one read-only Zetaris statement; the API key comes from the environment."""
    config = ZetarisConfig.from_env(os.environ)
    if config is None:
        raise ZetarisError("--facts-sql needs ZETARIS_API_KEY in the environment")
    return lambda: facts_block(run_sql(config, sql), sql)


def services_for(
    store: Store,
    runs_dir: Path,
    gateway_for: Callable[[Run], ModelGateway],
    facts: Callable[[], str] | None = None,
) -> Services:
    def load_request(run_id: str) -> str:
        return (run_dir(runs_dir, run_id) / REQUEST_FILE).read_text(encoding="utf-8")

    def save_spec(run_id: str, spec: ProjectSpec, cases: list[TestCase]) -> None:
        folder = run_dir(runs_dir, run_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SPEC_FILE).write_text(spec.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        tests = [case.model_dump(mode="json") for case in cases]
        (folder / TESTS_FILE).write_bytes(orjson.dumps(tests, option=orjson.OPT_INDENT_2) + b"\n")

    def emit_zetaris_error(run_id: str, message: str) -> None:
        store.append_events([
            RunEvent(
                run_id=run_id,
                seq=store.next_seq(run_id),
                ts=datetime.now(UTC),
                kind=EventKind.ERROR,
                payload={"message": message},
            )
        ])

    if facts is None:
        facts = default_facts(emit_event=emit_zetaris_error)

    return Services(
        preflight=preflight_for(store),
        gateway_for=gateway_for,
        load_run=store.get_run,
        load_request=load_request,
        record_call=store.record_llm_call,
        save_spec=save_spec,
        facts=facts,
    )
