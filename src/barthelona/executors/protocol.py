"""Executor protocol — every execution environment implements this (architecture §12)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId


@runtime_checkable
class Executor(Protocol):
    """Runs commands inside a sandboxed execution environment.

    Implementations: WslExecutor (bart-tc / bart-run via the WSL agent),
    FakeExecutor (tests).  Each executor may only run commands its
    ``may_run_untrusted`` flag permits.
    """

    @property
    def executor_id(self) -> ExecutorId:
        """Identifies the environment (``tc``, ``sandbox``, ``emu``, …)."""
        ...

    @property
    def may_run_untrusted(self) -> bool:
        """True only for the sandbox executor (bart-run)."""
        ...

    def probe(self) -> dict[str, str]:
        """Discover installed tools and return ``{tool_name: version_string}``.

        The result is used by :func:`barthelona.toolchains.probe.run_probe` to
        build ``config/toolchains.lock.json``.
        """
        ...

    def stage(self, sources: bytes) -> None:
        """Upload a tar archive of source files into the execution environment."""
        ...

    def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        """Run *cmd* inside the execution environment and return its result."""
        ...

    def collect(self) -> bytes:
        """Download a tar archive of build artifacts from the execution environment."""
        ...
