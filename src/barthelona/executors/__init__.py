"""Executor abstraction layer (architecture §12).

An executor is the boundary between the worker and the OS / container.
All commands pass through it as :class:`Command` argv tuples — shell strings
never appear in engine or node code (invariant 9).

Public surface
--------------
:class:`Executor`      The structural protocol every implementation satisfies.
:class:`FakeExecutor`  In-memory executor for unit tests.
:class:`WslExecutor`   Production executor: routes through the WSL agent
                       to ``bart-tc`` and ``bart-run`` Docker containers.
                       Raises :class:`WslUnavailableError` on non-Windows hosts.
:class:`WslUnavailableError`  Raised by WslExecutor on non-Windows platforms.
:data:`ExecutorId`     Literal type identifying which environment is active.
:class:`Command`       Frozen argv-plus-context value.
:class:`ExecLimits`    Per-call resource caps.
:class:`ExecResult`    Outcome of a single command.
"""

from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId
from barthelona.executors.fake import FakeExecutor
from barthelona.executors.protocol import Executor
from barthelona.executors.wsl import WslExecutor, WslUnavailableError

__all__ = [
    "Command",
    "ExecLimits",
    "ExecResult",
    "Executor",
    "ExecutorId",
    "FakeExecutor",
    "WslExecutor",
    "WslUnavailableError",
]
