"""Unit tests for toolchain probe logic (no WSL or Docker required)."""

from __future__ import annotations

from barthelona.executors import ExecResult, FakeExecutor
from barthelona.toolchains import ToolInfo, probe_image_digest, probe_tools, run_probe


def _fake_exec(image_digest: str = "sha256:tc000") -> FakeExecutor:
    """FakeExecutor with the default toolchain; digests come from ``image_digest``."""
    return FakeExecutor(image_digest=image_digest)


async def test_probe_tools_returns_all_standard_tools() -> None:
    session = await _fake_exec().open_session("probe", 0)
    tools = await probe_tools(session)
    assert set(tools.keys()) == {"nasm", "as", "ld", "gcc", "nm", "make", "gdb"}


async def test_probe_tools_version_content() -> None:
    session = await _fake_exec().open_session("probe", 0)
    tools = await probe_tools(session)
    assert tools["nasm"].version.startswith("NASM version")
    assert tools["nasm"].path == "/usr/bin/nasm"


async def test_probe_tools_skips_missing_tool() -> None:
    """A tool whose --version fails is omitted from the result."""
    missing = ExecResult(returncode=127, stdout=b"", stderr=b"not found", elapsed=0.001)
    session = await FakeExecutor(responses={("nasm", "--version"): missing}).open_session("probe", 0)
    tools = await probe_tools(session)
    assert "nasm" not in tools
    assert "as" in tools


async def test_probe_image_digest() -> None:
    assert await probe_image_digest(_fake_exec("sha256:tc999"), "bart-tc") == "sha256:tc999"


async def test_probe_image_digest_failure() -> None:
    """Returns empty string when the digest cannot be read."""
    assert await probe_image_digest(_fake_exec(""), "missing-img") == ""


async def test_run_probe_produces_toolchain_lock() -> None:
    lock = await run_probe(_fake_exec())
    assert lock.toolchain_image_digest == "sha256:tc000"
    assert lock.runner_image_digest == "sha256:tc000"
    assert "nasm" in lock.tools
    assert isinstance(lock.tools["nasm"], ToolInfo)
    assert lock.probed_at is not None


async def test_run_probe_timestamp_is_utc() -> None:
    lock = await run_probe(_fake_exec())
    assert lock.probed_at.tzinfo is not None
    # Should be very close to now; just confirm it parses.
    assert lock.probed_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
