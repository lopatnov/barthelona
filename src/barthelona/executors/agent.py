"""AgentExecutor — runs tool commands in ``bart-tc`` through the stdlib agent (D-043)."""

from __future__ import annotations

import base64
import re
import time
from pathlib import PurePosixPath
from typing import Any

from barthelona.executors._link import AgentLink, AgentTransport
from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId

_TC_CONTAINER = "bart-tc"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


class ExecutorRejectedError(RuntimeError):
    """The agent refused a request (allow-list, path fence); a bug in the caller, not a tool failure."""


def _unwrap(reply: dict[str, Any]) -> dict[str, Any]:
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
        reply = _unwrap(
            await self._link.request(
                {
                    "cmd": ["tar", "-xf", "-", "-C", self._work_dir],
                    "stdin": base64.b64encode(sources).decode(),
                }
            )
        )
        if reply["returncode"] != 0:
            raise RuntimeError(f"stage() failed: {base64.b64decode(reply.get('stderr', ''))!r}")

    async def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        lim = limits or ExecLimits(timeout=cmd.timeout)
        t0 = time.monotonic()
        reply = _unwrap(
            await self._link.request(
                {
                    "cmd": ["docker", "exec", self._container, *cmd.argv],
                    "cwd": cmd.cwd,
                    "env": cmd.env,
                    "stdin": base64.b64encode(cmd.stdin).decode() if cmd.stdin else None,
                    "timeout": lim.timeout,
                }
            )
        )
        return ExecResult(
            returncode=reply["returncode"],
            stdout=base64.b64decode(reply.get("stdout", ""))[: lim.max_stdout_bytes],
            stderr=base64.b64decode(reply.get("stderr", ""))[: lim.max_stderr_bytes],
            elapsed=time.monotonic() - t0,
        )

    async def collect(self) -> bytes:
        reply = _unwrap(await self._link.request({"cmd": ["tar", "-cf", "-", "-C", self._work_dir, "."]}))
        if reply["returncode"] != 0:
            raise RuntimeError(f"collect() failed: {base64.b64decode(reply.get('stderr', ''))!r}")
        return base64.b64decode(reply.get("stdout", ""))


class AgentExecutor:
    """Toolchain executor: ``docker exec bart-tc <argv>`` through an :class:`AgentTransport`.

    Use ``AgentExecutor(WslTransport())`` on Windows and ``AgentExecutor(LocalTransport())``
    on a Linux host with Docker. The agent link starts on the first call.
    """

    def __init__(self, transport: AgentTransport, container: str = _TC_CONTAINER) -> None:
        self._link = AgentLink(transport)
        self._container = container

    @property
    def executor_id(self) -> ExecutorId:
        return "tc"

    @property
    def may_run_untrusted(self) -> bool:
        return False

    async def open_session(self, run_id: str, attempt: int) -> AgentSession:
        if not _RUN_ID.fullmatch(run_id) or attempt < 0:
            raise ValueError(f"invalid session id: run_id={run_id!r} attempt={attempt!r}")
        await self._link.start()
        work_dir = f"{self._link.cache_root}/runs/{run_id}/{attempt}"
        return AgentSession(self._link, self._container, work_dir)

    async def image_digest(self, image: str) -> str:
        reply = _unwrap(
            await self._link.request(
                {"cmd": ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", image], "timeout": 10}
            )
        )
        if reply["returncode"] != 0:
            return ""
        return (
            base64.b64decode(reply.get("stdout", ""))
            .decode("utf-8", errors="replace")
            .split("\n", 1)[0]
            .strip()
        )

    async def aclose(self) -> None:
        self._link.close()
