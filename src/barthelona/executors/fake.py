"""FakeExecutor — in-memory executor for unit tests (no WSL or Docker needed)."""

from __future__ import annotations

from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId

_DEFAULT_TOOLS: dict[str, str] = {
    "nasm": "NASM version 2.16.03 compiled on Oct  1 2024",
    "as": "GNU assembler (GNU Binutils for Ubuntu) 2.42",
    "ld": "GNU ld (GNU Binutils for Ubuntu) 2.42",
    "gcc": "gcc (Ubuntu 15.2.0-1ubuntu1) 15.2.0",
    "nm": "GNU nm (GNU Binutils for Ubuntu) 2.42",
    "make": "GNU Make 4.4.1",
    "gdb": "GNU gdb (Ubuntu 16.1-0ubuntu2) 16.1",
}

_DEFAULT_PATHS: dict[str, str] = {
    "nasm": "/usr/bin/nasm",
    "as": "/usr/bin/as",
    "ld": "/usr/bin/ld",
    "gcc": "/usr/bin/gcc",
    "nm": "/usr/bin/nm",
    "make": "/usr/bin/make",
    "gdb": "/usr/bin/gdb",
}


class FakeExecutor:
    """An executor that runs entirely in memory.

    Useful for testing toolchain-probe logic and node logic without any
    real assembler, WSL, or Docker installation.

    Parameters
    ----------
    executor_id:
        The executor role this fake impersonates.
    may_run_untrusted:
        Mirrors the real executor's sandbox flag.
    tools:
        Map of tool name → first output line returned by ``--version``.
        Defaults to a representative Ubuntu 26.04 toolchain.
    paths:
        Map of tool name → path returned by ``which``.
    responses:
        Explicit ``{argv_tuple: ExecResult}`` overrides.  Any command not
        found here returns ``returncode=0`` with empty output.
    image_digest:
        Value returned when a caller asks for the container image digest.
    """

    def __init__(
        self,
        executor_id: ExecutorId = "tc",
        may_run_untrusted: bool = False,
        tools: dict[str, str] | None = None,
        paths: dict[str, str] | None = None,
        responses: dict[tuple[str, ...], ExecResult] | None = None,
        image_digest: str = "sha256:fake0000",
    ) -> None:
        self._executor_id = executor_id
        self._may_run_untrusted = may_run_untrusted
        self._tools = tools if tools is not None else dict(_DEFAULT_TOOLS)
        self._paths = paths if paths is not None else dict(_DEFAULT_PATHS)
        self._responses = responses or {}
        self._image_digest = image_digest
        self._staged: bytes | None = None

    # ------------------------------------------------------------------
    # Executor protocol
    # ------------------------------------------------------------------

    @property
    def executor_id(self) -> ExecutorId:
        return self._executor_id

    @property
    def may_run_untrusted(self) -> bool:
        return self._may_run_untrusted

    def probe(self) -> dict[str, str]:
        return dict(self._tools)

    def stage(self, sources: bytes) -> None:
        self._staged = sources

    def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        if cmd.argv in self._responses:
            return self._responses[cmd.argv]

        # Handle tool-version and which commands automatically.
        if len(cmd.argv) == 2 and cmd.argv[1] == "--version":
            tool = cmd.argv[0]
            if tool in self._tools:
                return ExecResult(
                    returncode=0,
                    stdout=(self._tools[tool] + "\n").encode(),
                    stderr=b"",
                    elapsed=0.001,
                )
        if len(cmd.argv) == 2 and cmd.argv[0] == "which":
            tool = cmd.argv[1]
            if tool in self._paths:
                return ExecResult(
                    returncode=0,
                    stdout=(self._paths[tool] + "\n").encode(),
                    stderr=b"",
                    elapsed=0.001,
                )

        # Handle docker inspect for image digest.
        if (
            len(cmd.argv) >= 4
            and cmd.argv[0] == "docker"
            and cmd.argv[1] == "inspect"
            and "--format" in cmd.argv
        ):
            return ExecResult(
                returncode=0,
                stdout=(self._image_digest + "\n").encode(),
                stderr=b"",
                elapsed=0.001,
            )

        return ExecResult(returncode=0, stdout=b"", stderr=b"", elapsed=0.001)

    def collect(self) -> bytes:
        return b""

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @property
    def staged(self) -> bytes | None:
        """Return the last archive uploaded via :meth:`stage`."""
        return self._staged
