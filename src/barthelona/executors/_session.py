"""AgentSession — an attempt's work directory driven through the agent link (D-043)."""

from __future__ import annotations

import base64
import time
from pathlib import PurePosixPath
from typing import Any

from barthelona.executors._link import AgentLink
from barthelona.executors._types import Command, ExecLimits, ExecResult


class ExecutorRejectedError(RuntimeError):
    """The agent refused a request (allow-list, path fence); a bug in the caller, not a tool failure."""


def unwrap(reply: dict[str, Any]) -> dict[str, Any]:
    if reply.get("rejected"):
        raise ExecutorRejectedError(str(reply.get("stderr", "")))
    return reply


class AgentSession:
    """An attempt's work directory under the agent's cache root."""

    def __init__(self, link: AgentLink, container: str, work_dir: str) -> None:
        self._link = link
        self._container = container
        self._work_dir = work_dir

    @property
    def work_dir(self) -> str:
        return self._work_dir

    def path(self, name: str) -> str:
        return str(PurePosixPath(self._work_dir) / name)

    async def stage(self, sources: bytes) -> None:
        reply = unwrap(
            await self._link.request(
                {
                    "cmd": ["tar", "-xf", "-", "-C", self._work_dir],
                    "stdin": base64.b64encode(sources).decode(),
                }
            )
        )
        if reply["returncode"] != 0:
            raise RuntimeError(f"stage() failed: {base64.b64decode(reply.get('stderr', ''))!r}")

    def _request(self, cmd: Command, lim: ExecLimits) -> dict[str, Any]:
        """The agent request for *cmd*; sessions of other environments override this."""
        return {
            "cmd": ["docker", "exec", self._container, *cmd.argv],
            "cwd": cmd.cwd,
            "env": cmd.env,
            "stdin": base64.b64encode(cmd.stdin).decode() if cmd.stdin else None,
            "timeout": lim.timeout,
        }

    async def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        lim = limits or ExecLimits(timeout=cmd.timeout)
        t0 = time.monotonic()
        reply = unwrap(await self._link.request(self._request(cmd, lim)))
        return ExecResult(
            returncode=reply["returncode"],
            stdout=base64.b64decode(reply.get("stdout", ""))[: lim.max_stdout_bytes],
            stderr=base64.b64decode(reply.get("stderr", ""))[: lim.max_stderr_bytes],
            elapsed=time.monotonic() - t0,
        )

    async def collect(self) -> bytes:
        reply = unwrap(await self._link.request({"cmd": ["tar", "-cf", "-", "-C", self._work_dir, "."]}))
        if reply["returncode"] != 0:
            raise RuntimeError(f"collect() failed: {base64.b64decode(reply.get('stderr', ''))!r}")
        return base64.b64decode(reply.get("stdout", ""))
