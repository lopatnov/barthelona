"""WslTransport — reach the stdlib agent through ``wsl.exe`` (architecture §12).

Windows only. The agent file is deployed to ``~/.local/share/barthelona/agent.py``
inside the distro by the worker; the worker verifies its sha256 first.
"""

from __future__ import annotations

import os
import sys

from barthelona.executors._link import ProcessTransport

#: Path inside WSL where the agent is deployed.
_AGENT_WSL_PATH = "~/.local/share/barthelona/agent.py"

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
        super().__init__(
            ["wsl.exe", "-d", distro, "-e", "python3", "-u", _AGENT_WSL_PATH],
            env={**os.environ, "WSL_UTF8": "1"},
        )
