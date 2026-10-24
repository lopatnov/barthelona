"""The worker's host-side services: where requests and specs live on disk, and the store behind the nodes.

A run's files sit in `runs/<run_id>/` (docs/architecture.md §18): the UI writes `request.txt` when it queues
the run, the engine writes `spec.json` for gate G1.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from barthelona.domain import ProjectSpec, Run
from barthelona.engine.graph import Services
from barthelona.engine.preflight import preflight_for
from barthelona.llm.gateway import ModelGateway
from barthelona.persistence import Store

REQUEST_FILE = "request.txt"
SPEC_FILE = "spec.json"


def run_dir(runs_dir: Path, run_id: str) -> Path:
    return runs_dir / run_id


def services_for(store: Store, runs_dir: Path, gateway_for: Callable[[Run], ModelGateway]) -> Services:
    def load_request(run_id: str) -> str:
        return (run_dir(runs_dir, run_id) / REQUEST_FILE).read_text(encoding="utf-8")

    def save_spec(run_id: str, spec: ProjectSpec) -> None:
        folder = run_dir(runs_dir, run_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SPEC_FILE).write_text(spec.model_dump_json(indent=2), encoding="utf-8", newline="\n")

    return Services(
        preflight=preflight_for(store),
        gateway_for=gateway_for,
        load_run=store.get_run,
        load_request=load_request,
        record_call=store.record_llm_call,
        save_spec=save_spec,
    )
