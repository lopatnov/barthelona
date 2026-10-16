"""Integration tests for WslExecutor (requires WSL and Docker on Windows)."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.wsl


@pytest.mark.skipif(sys.platform != "win32", reason="WslExecutor requires Windows")
def test_wsl_executor_probe_round_trip() -> None:
    """WslExecutor.probe() returns a non-empty tool map on a real bart-tc container."""
    from barthelona.executors import WslExecutor

    with WslExecutor() as exc:
        tools = exc.probe()

    assert "nasm" in tools, "nasm not found in bart-tc container"
    assert "as" in tools, "GNU as not found in bart-tc container"


@pytest.mark.skipif(sys.platform != "win32", reason="WslExecutor requires Windows")
def test_wsl_unavailable_on_linux() -> None:
    """This test only runs on Linux to confirm the guard raises."""
    pytest.skip("running on Windows; use the non-wsl test below")


def test_wsl_unavailable_error_raised_on_non_windows() -> None:
    """WslExecutor raises WslUnavailableError on non-Windows hosts."""
    if sys.platform == "win32":
        pytest.skip("test only meaningful on non-Windows")

    from barthelona.executors import WslUnavailableError, WslExecutor

    with pytest.raises(WslUnavailableError):
        WslExecutor()
