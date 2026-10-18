"""WslTransport — reach the stdlib agent through ``wsl.exe`` (architecture §12).

Windows only. ``start()`` deploys the agent source to ``~/.local/share/barthelona/agent.py``
inside the distro, then runs it. ``wsl.exe -e`` has no shell to expand ``~``, so both steps go
through a fixed ``sh -c`` string that uses ``$HOME``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from barthelona.executors._link import ExecutorInfraError, ProcessTransport

_AGENT_SOURCE = Path(__file__).with_name("_wsl_agent.py")

#: Fixed shell snippets run inside WSL; nothing from the caller is interpolated into them.
_AGENT_FILE = '"$HOME/.local/share/barthelona/agent.py"'
_DEPLOY_SCRIPT = (
    'mkdir -p "$HOME/.local/share/barthelona" && '
    f"cat > {_AGENT_FILE}.tmp && mv {_AGENT_FILE}.tmp {_AGENT_FILE}"
)
_RUN_SCRIPT = f"exec python3 -u {_AGENT_FILE}"
_DEPLOY_TIMEOUT_S = 60

#: Distro name used for all WSL calls.
_WSL_DISTRO = "Ubuntu"


class WslUnavailableError(RuntimeError):
    """Raised when WSL is not reachable or not available on this platform."""


class WslTransport(ProcessTransport):
    """Runs the agent in a WSL distro; ``WSL_UTF8=1`` keeps ``wsl.exe`` output UTF-8."""

    def __init__(self, distro: str = _WSL_DISTRO) -> None:
        if sys.platform != "win32":
            raise WslUnavailableError(
                "WslTransport requires Windows (wsl.exe).  "
                "On Linux use LocalTransport, or FakeExecutor in unit tests."
            )
        self._distro: str = distro
        self._wsl_env: dict[str, str] = {**os.environ, "WSL_UTF8": "1"}
        super().__init__(["wsl.exe", "-d", distro, "-e", "sh", "-c", _RUN_SCRIPT], env=self._wsl_env)

    def start(self) -> None:
        self._deploy_agent()
        super().start()

    def _deploy_agent(self) -> None:
        """Copy the agent source into the distro, so the file the agent runs from always exists."""
        source = _AGENT_SOURCE.read_bytes().replace(b"\r\n", b"\n")
        try:
            result = subprocess.run(  # noqa: S603  -- fixed wsl.exe argv and a constant sh script; shell=False
                ["wsl.exe", "-d", self._distro, "-e", "sh", "-c", _DEPLOY_SCRIPT],  # noqa: S607  -- wsl.exe is resolved from PATH
                input=source,
                capture_output=True,
                env=self._wsl_env,
                timeout=_DEPLOY_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutorInfraError(
                f"could not deploy the agent into WSL distro {self._distro!r}: {exc}"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ExecutorInfraError(
                f"could not deploy the agent into WSL distro {self._distro!r} "
                f"(exit {result.returncode}): {detail or 'no output; is the distro installed and running?'}"
            )
