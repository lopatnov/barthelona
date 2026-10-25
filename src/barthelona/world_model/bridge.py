"""The real TypeScript World Model, reached through `npx tsx` (D-058).

The production store is the Python `WorldModel`; this bridge drives the TypeScript reference in
`engines/world-model/index.ts` through a small NDJSON runner, so the slow integration test can prove the two
implementations derive the same stable IDs and both return an empty diff on re-ingest. Node is never required:
when `npx` or `tsx` is missing, `TsWorldModelUnavailable` is raised and the test skips.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from barthelona.world_model.types import WorldEntity, utc_now

# The runner under engines/world-model/bridge, resolved relative to this file (src/barthelona/world_model/).
_BRIDGE = Path(__file__).resolve().parents[3] / "engines" / "world-model" / "bridge" / "cli.ts"


class TsWorldModelUnavailable(RuntimeError):
    """Node (`npx tsx`) is not installed, refused to start or answered with an error."""


def _argv(bridge: Path) -> list[str]:
    npx = shutil.which("npx")
    if npx is None:
        raise TsWorldModelUnavailable("npx is not installed; the TypeScript World Model is skipped")
    argv = [npx, "--yes", "tsx", str(bridge)]
    # `npx` resolves to a .cmd on Windows; CreateProcess runs it through cmd.exe, never a shell string.
    if sys.platform == "win32" and npx.lower().endswith((".cmd", ".bat")):
        argv = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *argv]
    return argv


class TsWorldModel:
    """One subprocess per operation over a file-backed TypeScript World Model (bounded by a timeout)."""

    def __init__(self, directory: Path, namespace: str = "barthelona", timeout_s: float = 30.0) -> None:
        self._bridge = _BRIDGE
        self._directory = directory
        self._namespace = namespace
        self._timeout_s = timeout_s
        directory.mkdir(parents=True, exist_ok=True)
        self._run({"op": "ping"})

    def upsert(self, entity: WorldEntity) -> bool:
        provenance = entity.provenance
        if not provenance.at:
            provenance = replace(provenance, at=utc_now())
        result = self._run(
            {
                "op": "upsert",
                "kind": entity.kind,
                "key": entity.key,
                "attrs": entity.attrs,
                "source": provenance.as_dict(),
            }
        )
        return bool(result.get("changed"))

    def entities(self, run_id: str | None = None) -> list[dict[str, Any]]:
        result = self._run({"op": "list", "run_id": run_id})
        return list(result.get("entities", []))

    def close(self) -> None:
        """Nothing is held open: every operation is a fresh, bounded subprocess."""

    def _run(self, command: dict[str, Any]) -> dict[str, Any]:
        command = command | {"namespace": self._namespace, "directory": str(self._directory)}
        try:
            completed = subprocess.run(  # noqa: S603  # argv is a fixed bridge path, never run data
                _argv(self._bridge),
                input=json.dumps(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TsWorldModelUnavailable(f"the TypeScript World Model did not answer: {exc}") from exc
        if completed.returncode != 0:
            raise TsWorldModelUnavailable(f"the TypeScript World Model failed: {completed.stderr[-400:]}")
        try:
            result = json.loads(completed.stdout)
        except ValueError as exc:
            raise TsWorldModelUnavailable(
                f"the TypeScript World Model did not answer with JSON: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise TsWorldModelUnavailable("the TypeScript World Model did not answer with a JSON object")
        if "error" in result:
            raise TsWorldModelUnavailable(str(result["error"]))
        return result


def is_available() -> bool:
    """Whether `npx` is on PATH (used by the slow test to decide whether to run)."""
    try:
        _argv(_BRIDGE)
    except TsWorldModelUnavailable:
        return False
    return True
