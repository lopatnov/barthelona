"""Executor abstraction layer (architecture §12).

An executor is the boundary between the worker and the OS / container.
All commands pass through it as :class:`Command` argv tuples — shell strings
never appear in engine or node code (invariant 9).

Public surface
--------------
:class:`Executor`      Opens one :class:`Session` per run attempt (async, D-043).
:class:`Session`       Owns an attempt's work directory: ``stage``, ``run``, ``collect``.
:class:`AgentExecutor` Production executor: ``docker exec bart-tc`` through the
                       stdlib agent, over a transport.
:class:`SandboxExecutor` Runs generated binaries in a fresh ``bart-run`` container
                       (from :meth:`AgentExecutor.sandbox`).
:class:`WslTransport`  Reaches the agent through ``wsl.exe`` (Windows only;
                       raises :class:`WslUnavailableError` elsewhere).
:class:`LocalTransport` Spawns the same agent on a Linux host with Docker.
:class:`FakeExecutor`  In-memory executor for unit tests.
:data:`ExecutorId`     Literal type identifying which environment is active.
:class:`Command`       Frozen argv-plus-context value.
:class:`ExecLimits`    Per-call resource caps.
:class:`ExecResult`    Outcome of a single command.
"""

from barthelona.executors._link import AgentTransport, ExecutorInfraError
from barthelona.executors._session import ExecutorRejectedError
from barthelona.executors._types import Command, ExecLimits, ExecResult, ExecutorId
from barthelona.executors.agent import AgentExecutor
from barthelona.executors.fake import FakeExecutor
from barthelona.executors.local import LocalTransport
from barthelona.executors.protocol import Executor, Session
from barthelona.executors.sandbox import SandboxExecutor
from barthelona.executors.wsl import WslTransport, WslUnavailableError

__all__ = [
    "AgentExecutor",
    "AgentTransport",
    "Command",
    "ExecLimits",
    "ExecResult",
    "Executor",
    "ExecutorId",
    "ExecutorInfraError",
    "ExecutorRejectedError",
    "FakeExecutor",
    "LocalTransport",
    "SandboxExecutor",
    "Session",
    "WslTransport",
    "WslUnavailableError",
]
