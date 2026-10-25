"""The worker's host-side services: where requests and specs live on disk, and the store behind the nodes.

A run's files sit in `runs/<run_id>/` (docs/architecture.md §18): the UI writes `request.txt` when it queues
the run, the engine writes `spec.json` and `tests.json` for gate G1. The names and the folder come from
`barthelona.domain.layout`, which the UI also reads, so nothing here is the UI's only copy (invariant 8).
"""

from __future__ import annotations

import os
import shutil
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
from barthelona.domain.layout import (
    ATTEMPT_FILE,
    DRAFTS_DIR,
    REQUEST_FILE,
    SOURCE_FILE,
    SPEC_FILE,
    TESTS_FILE,
    run_dir,
)
from barthelona.engine.graph import Services
from barthelona.engine.preflight import preflight_for
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.hmem import HMem
from barthelona.llm.zetaris import ZetarisConfig, ZetarisError, facts_block, run_sql
from barthelona.persistence import Store
from barthelona.verification.asm_gate import find_nasm

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


class RunFolders:
    """Where a run's source files go: `var/runs/<id>/` and, when enabled, `<workspace>/drafts`."""

    def __init__(self, store: Store, runs_dir: Path, workspace_root: Path | None) -> None:
        self._store = store
        self._runs_dir = runs_dir
        self._workspace_root = workspace_root  # None: no copy in the project folder

    def _drafts(self, run_id: str) -> Path | None:
        if self._workspace_root is None:
            return None
        return self._workspace_root / self._store.get_run(run_id).workspace / DRAFTS_DIR

    def open(self, run_id: str) -> None:
        """Create the project folder when a run starts or restarts, and copy in drafts that predate it."""
        if (folder := self._drafts(run_id)) is None:
            return
        folder.mkdir(parents=True, exist_ok=True)
        source = run_dir(self._runs_dir, run_id)
        for name in (*sorted(p.name for p in source.glob(ATTEMPT_FILE.format(n="*"))), SOURCE_FILE):
            if (source / name).is_file() and not (folder / name).exists():
                shutil.copyfile(source / name, folder / name)  # drafts a run wrote before this folder existed

    def write(self, run_id: str, name: str, source: str) -> None:
        """Write one source file into the run folder and, when enabled, into the project's drafts folder."""
        for folder in (run_dir(self._runs_dir, run_id), self._drafts(run_id)):
            if folder is not None:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text(source + "\n", encoding="utf-8", newline="\n")


def services_for(
    store: Store,
    runs_dir: Path,
    gateway_for: Callable[[Run], ModelGateway],
    facts: Callable[[], str] | None = None,
    memory: HMem | None = None,
    nasm: str | None = None,
    workspace_root: Path | None = None,
) -> Services:
    def load_request(run_id: str) -> str:
        return (run_dir(runs_dir, run_id) / REQUEST_FILE).read_text(encoding="utf-8")

    def save_spec(run_id: str, spec: ProjectSpec, cases: list[TestCase]) -> None:
        folder = run_dir(runs_dir, run_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SPEC_FILE).write_text(spec.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        tests = [case.model_dump(mode="json") for case in cases]
        (folder / TESTS_FILE).write_bytes(orjson.dumps(tests, option=orjson.OPT_INDENT_2) + b"\n")

    folders = RunFolders(store, runs_dir, workspace_root)

    def save_source(run_id: str, source: str) -> None:
        folders.write(run_id, SOURCE_FILE, source)

    def save_attempt(run_id: str, attempt: int, source: str) -> None:
        folders.write(run_id, ATTEMPT_FILE.format(n=attempt), source)

    def emit_zetaris_error(run_id: str, message: str) -> None:
        store.append_events(
            [
                RunEvent(
                    run_id=run_id,
                    seq=store.next_seq(run_id),
                    ts=datetime.now(UTC),
                    kind=EventKind.ERROR,
                    payload={"message": message},
                )
            ]
        )

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
        save_source=save_source,
        save_attempt=save_attempt,
        open_workspace=folders.open,
        nasm=find_nasm(nasm),
        memory=memory,
    )
