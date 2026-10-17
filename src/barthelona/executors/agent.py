"""AgentExecutor — runs tool commands in ``bart-tc`` through the stdlib agent (D-043)."""

from __future__ import annotations

import base64
import re

from barthelona.executors._link import AgentLink, AgentTransport
from barthelona.executors._session import AgentSession, unwrap
from barthelona.executors._types import ExecutorId
from barthelona.executors.sandbox import SandboxExecutor

_TC_CONTAINER = "bart-tc"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


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
        reply = unwrap(
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

    def sandbox(self) -> SandboxExecutor:
        """The ``bart-run`` executor for generated binaries, sharing this executor's agent."""
        return SandboxExecutor(self._link, self.image_digest)

    async def aclose(self) -> None:
        self._link.close()
