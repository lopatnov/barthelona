"""Integration tests for the WSL transport (requires WSL and Docker on Windows)."""

from __future__ import annotations

import sys

import pytest

from barthelona.executors import AgentExecutor, Command, WslTransport, WslUnavailableError


@pytest.mark.wsl
@pytest.mark.skipif(sys.platform != "win32", reason="WslTransport requires Windows")
async def test_wsl_executor_toolchain_round_trip() -> None:
    """A real bart-tc container answers `nasm --version` and `as --version` through WSL."""
    executor = AgentExecutor(WslTransport())
    try:
        session = await executor.open_session("wsl-test", 0)
        nasm = await session.run(Command(argv=("nasm", "--version")))
        gnu_as = await session.run(Command(argv=("as", "--version")))
    finally:
        await executor.aclose()

    assert nasm.returncode == 0, "nasm not found in bart-tc container"
    assert gnu_as.returncode == 0, "GNU as not found in bart-tc container"


@pytest.mark.skipif(sys.platform == "win32", reason="only meaningful on non-Windows hosts")
def test_wsl_transport_unavailable_on_non_windows() -> None:
    with pytest.raises(WslUnavailableError):
        WslTransport()
