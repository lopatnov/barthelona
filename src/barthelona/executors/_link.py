"""Multiplexed link to the stdlib agent (architecture §12, D-043).

One long-lived agent process serves many concurrent requests. Each request
carries an ``id`` and each reply echoes it, so a slow command does not block
the others. Blocking pipe I/O lives in a reader thread; callers await futures.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import subprocess
import threading
from concurrent.futures import Future, InvalidStateError
from typing import Any, Protocol, runtime_checkable

#: Must equal ``PROTOCOL_VERSION`` in ``_wsl_agent.py``.
PROTOCOL_VERSION = 2

#: How much of the agent's stderr is kept for crash diagnostics.
STDERR_TAIL_BYTES = 4096
#: How long a failure path waits for the agent's last stderr bytes to be drained.
_STDERR_DRAIN_SECONDS = 0.5


class ExecutorInfraError(RuntimeError):
    """The agent link failed (no agent, protocol mismatch, pipe closed); not a tool failure."""


class AgentTransport(Protocol):
    """A byte pipe to one agent process."""

    def start(self) -> None:
        """Spawn the agent."""
        ...

    def write_line(self, data: bytes) -> None:
        """Send one newline-terminated line."""
        ...

    def read_line(self) -> bytes:
        """Block for one line; ``b""`` means the agent has gone away."""
        ...

    def close(self) -> None:
        """Stop the agent."""
        ...


@runtime_checkable
class StderrTail(Protocol):
    """A transport that keeps the end of the agent's stderr for crash diagnostics (#78)."""

    def stderr_tail(self) -> str:
        """The last :data:`STDERR_TAIL_BYTES` of the agent's stderr, decoded; empty when none."""
        ...


class ProcessTransport:
    """Transport over the stdin/stdout of a spawned process; the tail of its stderr is kept."""

    def __init__(self, argv: list[str], env: dict[str, str] | None = None) -> None:
        self._argv = argv
        self._env = env
        self._process: subprocess.Popen[bytes] | None = None
        self._stderr_buffer = bytearray()
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        self._stderr_buffer = bytearray()  # fresh per start: a late reader of a dead agent cannot write here
        self._process = subprocess.Popen(  # noqa: S603  -- argv is a fixed interpreter plus the agent path; shell=False
            self._argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self._process, self._stderr_buffer),
            name="agent-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    def _drain_stderr(self, process: subprocess.Popen[bytes], buffer: bytearray) -> None:
        """Read stderr until EOF so the pipe never fills, keeping only the last bytes in *buffer*."""
        assert process.stderr is not None  # noqa: S101  -- PIPE set in start()
        while chunk := process.stderr.read1(1024):
            with self._stderr_lock:
                buffer += chunk
                del buffer[:-STDERR_TAIL_BYTES]

    def stderr_tail(self) -> str:
        thread = self._stderr_thread
        if thread is not None:
            thread.join(timeout=_STDERR_DRAIN_SECONDS)  # a dead agent closes its stderr promptly
        with self._stderr_lock:
            return bytes(self._stderr_buffer).decode("utf-8", errors="replace").strip()

    def write_line(self, data: bytes) -> None:
        process = self._require()
        assert process.stdin is not None  # noqa: S101  -- PIPE set in start()
        process.stdin.write(data)
        process.stdin.flush()

    def read_line(self) -> bytes:
        process = self._require()
        assert process.stdout is not None  # noqa: S101  -- PIPE set in start()
        return process.stdout.readline()

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    def _require(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise ExecutorInfraError("agent transport is not started")
        return self._process


class AgentLink:
    """Request/reply multiplexer over an :class:`AgentTransport`."""

    def __init__(self, transport: AgentTransport) -> None:
        self._transport = transport
        self._ids = itertools.count(1)
        self._pending: dict[int, Future[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._started = False
        self._closed = False
        self._dead = False
        self._cache_root = ""

    @property
    def cache_root(self) -> str:
        """Absolute cache root reported by the agent; empty until the link has started."""
        return self._cache_root

    async def start(self) -> None:
        """Spawn the agent and complete the hello handshake; idempotent."""
        await asyncio.to_thread(self._ensure_started)

    async def request(self, payload: dict[str, object]) -> dict[str, Any]:
        """Send *payload*, await the reply with the same id."""
        await self.start()
        future: Future[dict[str, Any]] = Future()
        with self._lock:
            if self._closed or self._dead:
                raise ExecutorInfraError("agent link is closed")
            request_id = next(self._ids)
            self._pending[request_id] = future
        line = json.dumps({"id": request_id, **payload}, separators=(",", ":")).encode() + b"\n"
        try:
            await asyncio.to_thread(self._write, line)
        except (OSError, ExecutorInfraError) as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise ExecutorInfraError(f"agent pipe write failed: {exc}") from exc
        return await asyncio.wrap_future(future)

    def _write(self, line: bytes) -> None:
        with self._write_lock:  # one whole line at a time on the shared pipe
            self._transport.write_line(line)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._transport.close()
        self._fail_pending("agent link closed")

    def _ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._transport.start()
            try:
                hello = self._read_hello()
            except ExecutorInfraError:
                self._transport.close()
                raise
            self._cache_root = str(hello["cache_root"])
            self._started = True
            threading.Thread(target=self._read_loop, name="agent-link-reader", daemon=True).start()

    def _read_hello(self) -> dict[str, Any]:
        line = self._transport.read_line()
        if not line:
            raise ExecutorInfraError(self._with_stderr("agent exited before sending its hello"))
        try:
            hello = json.loads(line)["hello"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExecutorInfraError(f"agent hello is malformed: {line!r}") from exc
        if hello.get("protocol") != PROTOCOL_VERSION:
            raise ExecutorInfraError(
                f"agent speaks protocol {hello.get('protocol')!r}, expected {PROTOCOL_VERSION}"
            )
        return dict(hello)

    def _read_loop(self) -> None:
        try:
            while True:
                line = self._transport.read_line()
                if not line:
                    break
                self._route(line)
        except (OSError, ExecutorInfraError):
            pass
        finally:
            self._fail_pending(self._with_stderr("agent closed the pipe"))

    def _with_stderr(self, message: str) -> str:
        """*message* plus the agent's last stderr, when the transport kept any and we are not closing."""
        transport = self._transport
        if self._closed or not isinstance(transport, StderrTail):
            return message
        tail = transport.stderr_tail()
        return f"{message}; agent stderr: {tail}" if tail else message

    def _route(self, line: bytes) -> None:
        try:
            reply = json.loads(line)
            request_id = int(reply["id"])
        except (ValueError, KeyError, TypeError):
            return  # not a reply we can route; the request's own timeout surfaces it
        with self._lock:
            future = self._pending.pop(request_id, None)
        # A cancelled caller leaves a cancelled future behind; its late reply is dropped.
        if future is not None:
            with contextlib.suppress(InvalidStateError):
                future.set_result(reply)

    def _fail_pending(self, reason: str) -> None:
        with self._lock:
            self._dead = True
            pending, self._pending = self._pending, {}
        for future in pending.values():
            with contextlib.suppress(InvalidStateError):  # the caller may have cancelled it meanwhile
                future.set_exception(ExecutorInfraError(reason))
