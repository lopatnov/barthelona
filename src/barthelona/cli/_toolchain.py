"""Fail early, naming the fix, when the toolchain containers are not there (#129)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from barthelona.executors import AgentExecutor

_SETUP_LINUX = "scripts/setup-toolchain.sh"
_SETUP_WINDOWS = "wsl -d Ubuntu -e bash scripts/setup-toolchain.sh"


class ToolchainMissingError(RuntimeError):
    """``bart-tc`` is not running or ``bart-run`` is not built."""


async def ensure_toolchain(executor: AgentExecutor) -> None:
    """Raise :class:`ToolchainMissingError` with the setup command when a container is missing."""
    problems = await executor.toolchain_problems()
    if problems:
        command = _SETUP_WINDOWS if sys.platform == "win32" else _SETUP_LINUX
        raise ToolchainMissingError(f"{'; '.join(problems)}; set them up with `{command}`")
