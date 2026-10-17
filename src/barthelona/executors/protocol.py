"""Executor and Session protocols — every execution environment implements these (architecture §12, D-043)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId


@runtime_checkable
class Session(Protocol):
    """One attempt's isolated work directory inside an execution environment.

    Callers pass the tool argv (``nasm -f elf64 ...``) and build file arguments
    with :meth:`path`; the environment's own wrapper (``docker exec`` ...) stays
    inside the executor.
    """

    @property
    def work_dir(self) -> str:
        """Absolute path of the attempt's work directory as the tools see it."""
        ...

    def path(self, name: str) -> str:
        """Absolute path of *name* inside the work directory."""
        ...

    async def stage(self, sources: bytes) -> None:
        """Extract a tar archive of source files into the work directory."""
        ...

    async def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        """Run *cmd* (tool argv) in the environment and return its result."""
        ...

    async def collect(self) -> bytes:
        """Return a tar archive of the work directory contents."""
        ...


@runtime_checkable
class Executor(Protocol):
    """Opens sessions in one sandboxed execution environment.

    Implementations: :class:`~barthelona.executors.agent.AgentExecutor`
    (``bart-tc`` through the stdlib agent over a WSL or local transport) and
    :class:`~barthelona.executors.fake.FakeExecutor` (tests). The executor holds
    no per-attempt state, so tasks in flight cannot overwrite each other.
    """

    @property
    def executor_id(self) -> ExecutorId:
        """Identifies the environment (``tc``, ``sandbox``, ``emu``, …)."""
        ...

    @property
    def may_run_untrusted(self) -> bool:
        """True only for the sandbox executor (bart-run)."""
        ...

    async def open_session(self, run_id: str, attempt: int) -> Session:
        """Create the work directory for ``run_id`` / ``attempt`` and return its session."""
        ...

    async def image_digest(self, image: str) -> str:
        """Return the Docker image digest of *image*, or ``""`` when it cannot be read."""
        ...

    async def aclose(self) -> None:
        """Release the transport."""
        ...
