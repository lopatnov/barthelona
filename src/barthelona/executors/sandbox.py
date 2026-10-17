"""SandboxExecutor — runs generated binaries in a fresh ``bart-run`` container (D-043, invariant 2).

The agent owns every sandbox flag.  This side only names the image, the command
and the attempt's work directory, which the agent mounts read-only at ``/work``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable
from typing import Any

from barthelona.executors._link import AgentLink
from barthelona.executors._session import AgentSession
from barthelona.executors._types import Command, ExecLimits, ExecutorId

_RUN_IMAGE = "bart-run"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_STARTUP_SLACK = 5.0  # seconds for docker to create the container, on top of the program's own limit
_MOUNT = "/work"


class SandboxSession(AgentSession):
    """An attempt's work directory as the sandbox sees it: ``/work``, read-only.

    ``Command.cwd`` and ``Command.env`` are ignored: the program starts in the image's
    default directory with the image's environment.
    """

    def __init__(self, link: AgentLink, image: str, work_dir: str) -> None:
        super().__init__(link, container="", work_dir=work_dir)
        self._image = image

    def path(self, name: str) -> str:
        return f"{_MOUNT}/{name}"

    def _request(self, cmd: Command, lim: ExecLimits) -> dict[str, Any]:
        request = super()._request(cmd, lim)
        request["cwd"] = None  # these would apply to the host docker CLI, not the program
        request["env"] = None
        kill_after = max(1, math.ceil(lim.timeout))
        request["cmd"] = ["docker", "run", self._image, "timeout", "-s", "KILL", str(kill_after), *cmd.argv]
        request["mount"] = self.work_dir
        request["timeout"] = lim.timeout + _STARTUP_SLACK
        return request


class SandboxExecutor:
    """Executor for generated code; shares the toolchain executor's agent link."""

    def __init__(
        self,
        link: AgentLink,
        digest_of: Callable[[str], Awaitable[str]],
        image: str = _RUN_IMAGE,
    ) -> None:
        self._link = link
        self._digest_of = digest_of
        self._image = image

    @property
    def executor_id(self) -> ExecutorId:
        return "sandbox"

    @property
    def may_run_untrusted(self) -> bool:
        return True

    async def open_session(self, run_id: str, attempt: int) -> SandboxSession:
        if not _RUN_ID.fullmatch(run_id) or attempt < 0:
            raise ValueError(f"invalid session id: run_id={run_id!r} attempt={attempt!r}")
        await self._link.start()
        return SandboxSession(self._link, self._image, f"{self._link.cache_root}/runs/{run_id}/{attempt}")

    async def image_digest(self, image: str) -> str:
        return await self._digest_of(image)

    async def aclose(self) -> None:
        return None  # the link belongs to the AgentExecutor that created this executor
