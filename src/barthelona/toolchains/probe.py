"""Toolchain probe — discovers tool versions and writes ``config/toolchains.lock.json``.

Called by ``barthelona probe`` (architecture §12 Phase 0 deliverable).

The probe runs each tool ``--version`` and ``which`` inside the toolchain
environment via a :class:`~barthelona.executors.protocol.Session`, then records the
results alongside Docker image digests in :class:`ToolchainLock`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from barthelona.executors._types import Command, ExecLimits
from barthelona.toolchains._types import ToolchainLock, ToolInfo

if TYPE_CHECKING:
    from barthelona.executors.protocol import Executor, Session

_DEFAULT_TOOLS = ("nasm", "as", "ld", "gcc", "nm", "make", "gdb")
_TC_IMAGE = "bart-tc"
_RUN_IMAGE = "bart-run"
_LOCK_PATH = Path("config/toolchains.lock.json")


def _first_line(output: bytes) -> str:
    return output.decode("utf-8", errors="replace").split("\n", 1)[0].strip()


async def probe_image_digest(executor: Executor, image: str) -> str:
    """Return the Docker image digest for *image*, or ``""`` on failure."""
    return await executor.image_digest(image)


async def probe_tools(
    session: Session,
    tools: tuple[str, ...] = _DEFAULT_TOOLS,
) -> dict[str, ToolInfo]:
    """Probe each tool inside the toolchain environment and return a ``{name: ToolInfo}`` map."""
    lim = ExecLimits(timeout=10.0)
    result: dict[str, ToolInfo] = {}

    for tool in tools:
        version_res = await session.run(Command(argv=(tool, "--version")), lim)
        if version_res.returncode != 0:
            continue
        version = _first_line(version_res.stdout)

        which_res = await session.run(Command(argv=("which", tool)), lim)
        path = _first_line(which_res.stdout) if which_res.returncode == 0 else ""

        result[tool] = ToolInfo(version=version, path=path)

    return result


async def run_probe(
    executor: Executor,
    tools: tuple[str, ...] = _DEFAULT_TOOLS,
    tc_image: str = _TC_IMAGE,
    run_image: str = _RUN_IMAGE,
) -> ToolchainLock:
    """Run the full probe and return an unpersisted :class:`ToolchainLock`."""
    session = await executor.open_session("probe", 0)
    tool_map = await probe_tools(session, tools=tools)
    tc_digest = await probe_image_digest(executor, tc_image)
    run_digest = await probe_image_digest(executor, run_image)
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
