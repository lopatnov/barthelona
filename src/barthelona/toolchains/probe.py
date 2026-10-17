"""Toolchain probe — discovers tool versions and writes ``config/toolchains.lock.json``.

Called by ``barthelona probe`` (architecture §12 Phase 0 deliverable).

The probe runs each tool ``--version`` and ``which`` inside the ``bart-tc``
container via :class:`~barthelona.executors.protocol.Executor`, then records the
results alongside Docker image digests in :class:`ToolchainLock`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from barthelona.toolchains._types import ToolchainLock, ToolInfo

if TYPE_CHECKING:
    from barthelona.executors.protocol import Executor

_DEFAULT_TOOLS = ("nasm", "as", "ld", "gcc", "nm", "make", "gdb")
_TC_CONTAINER = "bart-tc"
_RUN_IMAGE = "bart-run"
_LOCK_PATH = Path("config/toolchains.lock.json")


def _first_line(output: bytes) -> str:
    return output.decode("utf-8", errors="replace").split("\n", 1)[0].strip()


def probe_image_digest(executor: Executor, image: str) -> str:
    """Return the Docker image digest for *image*, or ``""`` on failure."""
    from barthelona.executors._types import Command, ExecLimits

    cmd = Command(
        argv=(
            "docker",
            "inspect",
            "--format",
            "{{index .RepoDigests 0}}",
            image,
        )
    )
    result = executor.run(cmd, ExecLimits(timeout=10.0))
    if result.returncode != 0:
        return ""
    return _first_line(result.stdout)


def probe_tools(
    executor: Executor,
    tools: tuple[str, ...] = _DEFAULT_TOOLS,
    container: str = _TC_CONTAINER,
) -> dict[str, ToolInfo]:
    """Probe each tool inside *container* and return a ``{name: ToolInfo}`` map."""
    from barthelona.executors._types import Command, ExecLimits

    lim = ExecLimits(timeout=10.0)
    result: dict[str, ToolInfo] = {}

    for tool in tools:
        version_cmd = Command(argv=("docker", "exec", container, tool, "--version"))
        version_res = executor.run(version_cmd, lim)
        if version_res.returncode != 0:
            continue
        version = _first_line(version_res.stdout)

        which_cmd = Command(argv=("docker", "exec", container, "which", tool))
        which_res = executor.run(which_cmd, lim)
        path = _first_line(which_res.stdout) if which_res.returncode == 0 else ""

        result[tool] = ToolInfo(version=version, path=path)

    return result


def run_probe(
    executor: Executor,
    tools: tuple[str, ...] = _DEFAULT_TOOLS,
    tc_container: str = _TC_CONTAINER,
    run_image: str = _RUN_IMAGE,
) -> ToolchainLock:
    """Run the full probe and return an unpersisted :class:`ToolchainLock`."""
    tool_map = probe_tools(executor, tools=tools, container=tc_container)
    tc_digest = probe_image_digest(executor, tc_container)
    run_digest = probe_image_digest(executor, run_image)
    return ToolchainLock(
        toolchain_image_digest=tc_digest,
        runner_image_digest=run_digest,
        tools=tool_map,
        probed_at=datetime.now(UTC),
    )


def write_lock_file(lock: ToolchainLock, path: Path = _LOCK_PATH) -> None:
    """Write *lock* as JSON to *path*, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(lock.model_dump_json())
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_lock_file(path: Path = _LOCK_PATH) -> ToolchainLock:
    """Read and validate a lock file from *path*.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    pydantic.ValidationError
        If the JSON is structurally invalid.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ToolchainLock.model_validate(raw)
