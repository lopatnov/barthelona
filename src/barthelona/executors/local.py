"""LocalTransport — spawn the stdlib agent directly on a Linux host with Docker (D-043).

Used on GitHub Actions and cloud sessions where WSL does not exist. The agent's
allow-list, path fence and sandbox flags apply exactly as under WSL.
"""

from __future__ import annotations

import sys
from pathlib import Path

from barthelona.executors._link import ProcessTransport

_AGENT_SOURCE = Path(__file__).with_name("_wsl_agent.py")


class LocalTransport(ProcessTransport):
    """Runs the agent as a child of this process using the current interpreter."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        super().__init__([sys.executable, "-u", str(_AGENT_SOURCE)], env=env)
