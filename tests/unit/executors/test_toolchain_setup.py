"""A missing toolchain is named with its fix, and the WSL agent is deployed before it runs (#129)."""

from __future__ import annotations

import base64
import json
import queue
import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from barthelona.cli._toolchain import ToolchainMissingError, ensure_toolchain
from barthelona.executors import AgentExecutor, ExecutorInfraError
from barthelona.executors import wsl as wsl_module
from barthelona.executors._link import PROTOCOL_VERSION


def _hello() -> bytes:
    return json.dumps({"hello": {"protocol": PROTOCOL_VERSION, "cache_root": "/cache"}}).encode() + b"\n"


class ScriptedTransport:
    """In-process agent: answers each request via ``reply(request)`` lines."""

    def __init__(self, hello: bytes, reply: Callable[[dict[str, Any]], list[bytes]]) -> None:
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._hello = hello
        self._reply = reply

    def start(self) -> None:
        self._lines.put(self._hello)

    def write_line(self, data: bytes) -> None:
        for line in self._reply(json.loads(data)):
            self._lines.put(line)

    def read_line(self) -> bytes:
        return self._lines.get()

    def close(self) -> None:
        self._lines.put(b"")


def _inspect_reply(running: str, image: str) -> Callable[[dict[str, Any]], list[bytes]]:
    """Agent answering ``docker inspect`` for the container and the runner image."""

    def reply(request: dict[str, Any]) -> list[bytes]:
        target = request["cmd"][-1]
        out = running if target == "bart-tc" else image
        body = {
            "id": request["id"],
            "returncode": 0 if out else 1,
            "stdout": base64.b64encode(out.encode()).decode(),
            "stderr": "",
            "elapsed": 0.0,
        }
        return [json.dumps(body).encode() + b"\n"]

    return reply


async def test_a_complete_toolchain_has_no_problems() -> None:
    executor = AgentExecutor(ScriptedTransport(_hello(), _inspect_reply("true\n", "sha256:abc\n")))
    assert await executor.toolchain_problems() == []


async def test_missing_pieces_are_each_named() -> None:
    executor = AgentExecutor(ScriptedTransport(_hello(), _inspect_reply("", "")))
    problems = await executor.toolchain_problems()
    assert problems == ["the bart-tc container is not running", "the bart-run image is not built"]


async def test_ensure_toolchain_names_the_setup_script() -> None:
    executor = AgentExecutor(ScriptedTransport(_hello(), _inspect_reply("false\n", "sha256:abc\n")))
    with pytest.raises(ToolchainMissingError, match=r"not running.*setup-toolchain\.sh"):
        await ensure_toolchain(executor)


def _windows_transport(monkeypatch: pytest.MonkeyPatch) -> wsl_module.WslTransport:
    monkeypatch.setattr(wsl_module.sys, "platform", "win32")
    return wsl_module.WslTransport()


def test_wsl_deploys_the_agent_source_through_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(wsl_module.subprocess, "run", fake_run)
    _windows_transport(monkeypatch)._deploy_agent()
    assert calls[0]["argv"][:5] == ["wsl.exe", "-d", "Ubuntu", "-e", "sh"]
    assert b"PROTOCOL_VERSION" in calls[0]["input"]
    assert b"\r" not in calls[0]["input"]


def test_wsl_runs_the_deployed_agent_from_home(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _windows_transport(monkeypatch)
    assert transport._argv[-1] == 'exec python3 -u "$HOME/.local/share/barthelona/agent.py"'


def test_a_failed_deploy_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 1, b"", b"There is no distribution with the supplied name.")

    monkeypatch.setattr(wsl_module.subprocess, "run", failing)
    transport = _windows_transport(monkeypatch)
    with pytest.raises(ExecutorInfraError, match="no distribution"):
        transport._deploy_agent()
