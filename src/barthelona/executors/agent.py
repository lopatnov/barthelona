"""AgentExecutor — runs tool commands in ``bart-tc`` through the stdlib agent (D-043)."""

from __future__ import annotations

import base64
import re

from barthelona.executors._link import AgentLink, AgentTransport
from barthelona.executors._session import AgentSession, unwrap
from barthelona.executors._types import ExecutorId
from barthelona.executors.sandbox import SandboxExecutor

_TC_CONTAINER = "bart-tc"
_RUN_IMAGE = "bart-run"
_DIGEST_TEMPLATE = "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}"
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
        """The registry digest, or the image ID for an image built locally (no registry digest exists)."""
        return await self._inspect(image, _DIGEST_TEMPLATE, "--type=image")

    async def toolchain_problems(self, run_image: str = _RUN_IMAGE) -> list[str]:
        """What is missing before any tool can run: the ``bart-tc`` container, the runner image.

        Each entry names the missing piece; the fix for all of them is ``scripts/setup-toolchain.sh``.
        """
        problems: list[str] = []
        running = await self._inspect(self._container, "{{.State.Running}}")
        if running != "true":
            problems.append(f"the {self._container} container is not running")
        if not await self._inspect(run_image, "{{.Id}}"):
            problems.append(f"the {run_image} image is not built")
        return problems

    async def _inspect(self, target: str, template: str, *flags: str) -> str:
        """First line of ``docker inspect --format template target``; empty when docker fails."""
        reply = unwrap(
            await self._link.request(
                {"cmd": ["docker", "inspect", *flags, "--format", template, target], "timeout": 10}
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

    async def aclose(self) -> None:  # NOSONAR S7503: async is part of the Executor protocol
        self._link.close()
