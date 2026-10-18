"""AgentLink / AgentExecutor against scripted and real (local) agents. No Docker needed."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import queue
import sys
import tarfile
import time
from pathlib import Path

import pytest

from barthelona.executors import AgentExecutor, ExecutorInfraError, ExecutorRejectedError, LocalTransport
from barthelona.executors._link import PROTOCOL_VERSION, STDERR_TAIL_BYTES, AgentLink, ProcessTransport


def _hello(protocol: int = PROTOCOL_VERSION) -> bytes:
    return json.dumps({"hello": {"protocol": protocol, "cache_root": "/cache"}}).encode() + b"\n"


class ScriptedTransport:
    """In-process agent: answers each request via ``reply(request) -> list[bytes]`` lines."""

    def __init__(self, hello: bytes, reply) -> None:  # type: ignore[no-untyped-def]  # test helper
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._hello = hello
        self._reply = reply
        self.requests: list[dict[str, object]] = []

    def start(self) -> None:
        self._lines.put(self._hello)

    def write_line(self, data: bytes) -> None:
        request = json.loads(data)
        self.requests.append(request)
        for line in self._reply(request):
            self._lines.put(line)

    def read_line(self) -> bytes:
        return self._lines.get()

    def close(self) -> None:
        self._lines.put(b"")


def _ok(request: dict[str, object], stdout: bytes = b"") -> bytes:
    body = {
        "id": request["id"],
        "returncode": 0,
        "stdout": base64.b64encode(stdout).decode(),
        "stderr": "",
        "elapsed": 0.0,
    }
    return json.dumps(body).encode() + b"\n"


async def test_replies_are_routed_by_id_even_out_of_order() -> None:
    held: list[dict[str, object]] = []

    def reply(request: dict[str, object]) -> list[bytes]:
        if not held:  # hold the first request until the second one has arrived
            held.append(request)
            return []
        return [_ok(request, b"second"), _ok(held[0], b"first")]

    link = AgentLink(ScriptedTransport(_hello(), reply))
    first = asyncio.ensure_future(link.request({"cmd": ["a"]}))
    await asyncio.sleep(0.05)
    second = asyncio.ensure_future(link.request({"cmd": ["b"]}))
    assert base64.b64decode((await first)["stdout"]) == b"first"
    assert base64.b64decode((await second)["stdout"]) == b"second"
    link.close()


async def test_cancelled_request_does_not_break_the_link() -> None:
    held: list[dict[str, object]] = []

    def reply(request: dict[str, object]) -> list[bytes]:
        if not held:
            held.append(request)
            return []
        return [_ok(held[0]), _ok(request, b"later")]  # the first reply arrives after its caller gave up

    link = AgentLink(ScriptedTransport(_hello(), reply))
    first = asyncio.ensure_future(link.request({"cmd": ["a"]}))
    await asyncio.sleep(0.05)
    first.cancel()
    second = await asyncio.wait_for(link.request({"cmd": ["b"]}), timeout=2)
    assert base64.b64decode(second["stdout"]) == b"later"
    link.close()


async def test_request_after_agent_exit_fails_fast() -> None:
    link = AgentLink(ScriptedTransport(_hello(), lambda r: [b""]))
    with pytest.raises(ExecutorInfraError):
        await link.request({"cmd": ["a"]})
    second = link.request({"cmd": ["b"]})
    with pytest.raises(ExecutorInfraError):
        await asyncio.wait_for(second, timeout=2)


async def test_protocol_mismatch_is_an_infra_error() -> None:
    link = AgentLink(ScriptedTransport(_hello(protocol=1), lambda r: []))
    with pytest.raises(ExecutorInfraError, match="protocol"):
        await link.request({"cmd": ["a"]})


async def test_agent_exit_fails_pending_requests() -> None:
    link = AgentLink(ScriptedTransport(_hello(), lambda r: [b""]))
    with pytest.raises(ExecutorInfraError):
        await link.request({"cmd": ["a"]})


async def test_session_paths_use_the_agents_cache_root() -> None:
    exc = AgentExecutor(ScriptedTransport(_hello(), lambda r: [_ok(r)]))
    session = await exc.open_session("run1", 3)
    assert session.work_dir == "/cache/runs/run1/3"
    assert session.path("a.asm") == "/cache/runs/run1/3/a.asm"
    await exc.aclose()


@pytest.mark.parametrize(("run_id", "attempt"), [("../x", 0), ("a/b", 0), ("", 0), ("ok", -1)])
async def test_open_session_rejects_unsafe_ids(run_id: str, attempt: int) -> None:
    exc = AgentExecutor(ScriptedTransport(_hello(), lambda r: [_ok(r)]))
    with pytest.raises(ValueError, match="invalid session id"):
        await exc.open_session(run_id, attempt)


async def test_run_wraps_tool_argv_in_docker_exec() -> None:
    transport = ScriptedTransport(_hello(), lambda r: [_ok(r, b"NASM\n")])
    exc = AgentExecutor(transport)
    session = await exc.open_session("r", 0)
    from barthelona.executors import Command

    result = await session.run(Command(argv=("nasm", "--version")))
    assert result.stdout == b"NASM\n"
    assert transport.requests[-1]["cmd"] == ["docker", "exec", "bart-tc", "nasm", "--version"]
    await exc.aclose()


async def test_rejected_request_raises() -> None:
    def reject(request: dict[str, object]) -> list[bytes]:
        body = {
            "id": request["id"],
            "returncode": 1,
            "stdout": "",
            "stderr": "nope",
            "elapsed": 0,
            "rejected": True,
        }
        return [json.dumps(body).encode() + b"\n"]

    exc = AgentExecutor(ScriptedTransport(_hello(), reject))
    session = await exc.open_session("r", 0)
    from barthelona.executors import Command

    command = Command(argv=("x",))
    with pytest.raises(ExecutorRejectedError, match="nope"):
        await session.run(command)


def _names(archive: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        return tf.getnames()


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


async def test_local_agent_stages_and_collects_in_isolated_session_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real stdlib agent over LocalTransport: only `tar` is needed, not Docker."""
    monkeypatch.setenv("HOME", str(tmp_path))
    exc = AgentExecutor(LocalTransport(env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}))
    try:
        one = await exc.open_session("run", 0)
        two = await exc.open_session("run", 1)
        await asyncio.gather(one.stage(_tar({"a.asm": b"one"})), two.stage(_tar({"b.asm": b"two"})))
        names_one = _names(await one.collect())
        names_two = _names(await two.collect())
    finally:
        await exc.aclose()
    assert "./a.asm" in names_one
    assert "./b.asm" not in names_one
    assert "./b.asm" in names_two
    assert one.work_dir.startswith(str(tmp_path))


async def test_sandbox_session_runs_in_bart_run_with_a_read_only_mount() -> None:
    from barthelona.executors import Command, ExecLimits

    transport = ScriptedTransport(_hello(), lambda r: [_ok(r, b"out")])
    exc = AgentExecutor(transport)
    sandbox = exc.sandbox()
    assert sandbox.executor_id == "sandbox"
    assert sandbox.may_run_untrusted
    session = await sandbox.open_session("r", 2)
    assert session.path("output.elf") == "/work/output.elf"

    result = await session.run(Command(argv=("/work/output.elf",), stdin=b"hi"), ExecLimits(timeout=3.2))

    request = transport.requests[-1]
    assert result.stdout == b"out"
    assert request["cmd"] == ["docker", "run", "bart-run", "timeout", "-s", "KILL", "4", "/work/output.elf"]
    assert request["mount"] == "/cache/runs/r/2"
    assert request["timeout"] == 8.2
    assert base64.b64decode(str(request["stdin"])) == b"hi"
    await exc.aclose()


async def test_sandbox_open_session_rejects_unsafe_ids() -> None:
    sandbox = AgentExecutor(ScriptedTransport(_hello(), lambda r: [_ok(r)])).sandbox()
    with pytest.raises(ValueError, match="invalid session id"):
        await sandbox.open_session("../x", 0)


async def test_agent_stderr_is_in_the_infra_error() -> None:
    """#78: a crashing agent's traceback reaches the caller instead of being discarded."""
    crash = "import sys; sys.stderr.write('Traceback: boom'); sys.exit(1)"
    link = AgentLink(ProcessTransport([sys.executable, "-c", crash]))
    with pytest.raises(ExecutorInfraError, match="agent stderr: Traceback: boom"):
        await link.request({"cmd": ["a"]})


def test_stderr_tail_keeps_only_the_last_bytes() -> None:
    noisy = f"import sys; sys.stderr.write('x' * {STDERR_TAIL_BYTES * 3} + 'END')"
    transport = ProcessTransport([sys.executable, "-c", noisy])
    transport.start()
    deadline = time.monotonic() + 10
    tail = transport.stderr_tail()
    while not tail.endswith("END") and time.monotonic() < deadline:  # slow CI hosts drain late
        time.sleep(0.05)
        tail = transport.stderr_tail()
    transport.close()
    assert len(tail) == STDERR_TAIL_BYTES
    assert tail.endswith("END")
