"""WslExecutor — runs commands inside the WSL agent and Docker containers.

Architecture §12: the worker keeps one long-lived WSL agent process alive.
The agent speaks JSON lines; binary payloads are base64-encoded.

This module only works on Windows (requires ``wsl.exe`` and Docker).
On other platforms every method raises :class:`WslUnavailableError`.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId

if TYPE_CHECKING:
    pass  # keep imports light for non-Windows hosts

#: Path inside WSL where the agent is deployed.
_AGENT_WSL_PATH = PurePosixPath("~/.local/share/barthelona/agent.py")

#: Source path of the agent inside the installed package.
_AGENT_SOURCE = Path(__file__).with_name("_wsl_agent.py")

#: Distro name used for all WSL calls.
_WSL_DISTRO = "Ubuntu"

#: Default Docker container names.
_TC_CONTAINER = "bart-tc"

#: Default work directory under the cache root for stage/collect (architecture §12).
_DEFAULT_WORK_DIR = "~/.cache/barthelona/work"


class WslUnavailableError(RuntimeError):
    """Raised when WSL is not reachable or not available on this platform."""


class WslExecutor:
    """Executor that dispatches through the long-lived WSL agent (architecture §12).

    The agent process is started lazily on the first :meth:`run` call and
    kept alive until :meth:`close` is called.  Use as a context manager::

        with WslExecutor() as exc:
            result = exc.run(Command(argv=("nasm", "--version")))

    Parameters
    ----------
    container:
        Name of the long-lived toolchain container (``bart-tc`` by default).
    distro:
        WSL distro to start (``Ubuntu`` by default).
    work_dir:
        WSL path under ``~/.cache/barthelona/`` used by :meth:`stage` and
        :meth:`collect` as the per-run working directory.  The worker sets
        this to ``~/.cache/barthelona/runs/<run_id>/<attempt>/`` before each
        run (architecture §12).
    """

    def __init__(
        self,
        container: str = _TC_CONTAINER,
        distro: str = _WSL_DISTRO,
        work_dir: str = _DEFAULT_WORK_DIR,
    ) -> None:
        if sys.platform != "win32":
            raise WslUnavailableError(
                "WslExecutor requires Windows (wsl.exe).  "
                "On Linux, use FakeExecutor for tests or run the probe on a Windows host."
            )
        self._container = container
        self._distro = distro
        self._work_dir = work_dir
        self._process: subprocess.Popen[bytes] | None = None

    # ------------------------------------------------------------------
    # Executor protocol
    # ------------------------------------------------------------------

    @property
    def executor_id(self) -> ExecutorId:
        return "tc"

    @property
    def may_run_untrusted(self) -> bool:
        return False

    def probe(self) -> dict[str, str]:
        """Return ``{tool_name: first-version-line}`` for tools in the container."""
        tools = {}
        for tool in ("nasm", "as", "ld", "gcc", "nm", "make", "gdb"):
            result = self.run(
                Command(argv=("docker", "exec", self._container, tool, "--version")),
                ExecLimits(timeout=10.0),
            )
            if result.returncode == 0:
                out = result.stdout.decode("utf-8", errors="replace")
                tools[tool] = out.split("\n", 1)[0].strip()
        return tools

    def stage(self, sources: bytes) -> None:
        """Extract a tar archive of sources into the per-run work directory."""
        result = self._send(
            {
                "cmd": ["tar", "-xf", "-", "-C", self._work_dir],
                "stdin": base64.b64encode(sources).decode(),
                "timeout": 30,
            }
        )
        if result["returncode"] != 0:
            raise RuntimeError(f"stage() failed: {result.get('stderr', '')!r}")

    def run(self, cmd: Command, limits: ExecLimits | None = None) -> ExecResult:
        lim = limits or ExecLimits()
        t0 = time.monotonic()
        raw = self._send(
            {
                "cmd": list(cmd.argv),
                "cwd": cmd.cwd,
                "env": cmd.env,
                "stdin": base64.b64encode(cmd.stdin).decode() if cmd.stdin else None,
                "timeout": lim.timeout,
            }
        )
        elapsed = time.monotonic() - t0
        stdout = base64.b64decode(raw.get("stdout", ""))
        stderr = base64.b64decode(raw.get("stderr", ""))
        return ExecResult(
            returncode=raw["returncode"],
            stdout=stdout[: lim.max_stdout_bytes],
            stderr=stderr[: lim.max_stderr_bytes],
            elapsed=elapsed,
        )

    def collect(self) -> bytes:
        """Return a tar archive of the per-run work directory contents."""
        result = self._send({"cmd": ["tar", "-cf", "-", "-C", self._work_dir, "."]})
        if result["returncode"] != 0:
            raise RuntimeError(f"collect() failed: {result.get('stderr', '')!r}")
        return base64.b64decode(result.get("stdout", ""))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_started(self) -> None:
        if self._process is not None:
            return
        env = dict(os.environ)
        env["WSL_UTF8"] = "1"
        self._process = subprocess.Popen(  # noqa: S603  -- argv list; wsl.exe is a trusted Windows binary
            ["wsl.exe", "-d", self._distro, "-e", "python3", "-u", str(_AGENT_WSL_PATH)],  # noqa: S607 -- wsl.exe is on PATH on every Windows edition; a full path would break portability
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def _send(self, request: dict[str, object]) -> dict[str, object]:
        self._ensure_started()
        assert self._process is not None  # noqa: S101  -- None only before _ensure_started(); unreachable here
        assert self._process.stdin is not None  # noqa: S101  -- PIPE set in _ensure_started(); always non-None
        assert self._process.stdout is not None  # noqa: S101  -- PIPE set in _ensure_started(); always non-None
        line = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()
        response_line = self._process.stdout.readline()
        return dict(json.loads(response_line))  # type: ignore[arg-type]

    def close(self) -> None:
        if self._process is not None:
            try:
                self._process.stdin and self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:  # best-effort shutdown; kill on any error
                self._process.kill()
            self._process = None

    def __enter__(self) -> WslExecutor:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
