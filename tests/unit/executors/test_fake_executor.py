"""Unit tests for FakeExecutor (no WSL or Docker required)."""

from __future__ import annotations

from barthelona.executors import Command, ExecLimits, ExecResult, FakeExecutor, Session


def test_executor_id_default() -> None:
    assert FakeExecutor().executor_id == "tc"


def test_executor_id_custom() -> None:
    assert FakeExecutor(executor_id="sandbox").executor_id == "sandbox"


def test_may_run_untrusted_default() -> None:
    assert FakeExecutor().may_run_untrusted is False


async def test_session_paths_are_per_attempt() -> None:
    exc = FakeExecutor()
    first = await exc.open_session("run1", 0)
    second = await exc.open_session("run1", 1)
    assert isinstance(first, Session)
    assert first.work_dir != second.work_dir
    assert first.path("a.asm") == f"{first.work_dir}/a.asm"


async def test_version_command_auto() -> None:
    session = await FakeExecutor().open_session("r", 0)
    result = await session.run(Command(argv=("nasm", "--version")))
    assert result.returncode == 0
    assert b"NASM" in result.stdout


async def test_which_command_auto() -> None:
    session = await FakeExecutor().open_session("r", 0)
    result = await session.run(Command(argv=("which", "nasm")))
    assert result.returncode == 0
    assert b"/usr/bin/nasm" in result.stdout


async def test_image_digest() -> None:
    assert await FakeExecutor(image_digest="sha256:abc123").image_digest("bart-tc") == "sha256:abc123"


async def test_explicit_response_override() -> None:
    override = ExecResult(returncode=42, stdout=b"custom", stderr=b"", elapsed=0.0)
    session = await FakeExecutor(responses={("echo", "hi"): override}).open_session("r", 0)
    result = await session.run(Command(argv=("echo", "hi")))
    assert result.returncode == 42
    assert result.stdout == b"custom"


async def test_unknown_command_returns_zero() -> None:
    session = await FakeExecutor().open_session("r", 0)
    result = await session.run(Command(argv=("unknown-binary",)))
    assert result.returncode == 0
    assert result.stdout == b""


async def test_stage_stores_bytes() -> None:
    exc = FakeExecutor()
    session = await exc.open_session("r", 0)
    assert exc.staged is None
    await session.stage(b"archive-content")
    assert exc.staged == b"archive-content"


async def test_collect_returns_empty_bytes() -> None:
    session = await FakeExecutor().open_session("r", 0)
    assert await session.collect() == b""


async def test_custom_tools_override_defaults() -> None:
    session = await FakeExecutor(tools={"nasm": "NASM version 2.99"}).open_session("r", 0)
    result = await session.run(Command(argv=("nasm", "--version")))
    assert b"2.99" in result.stdout


async def test_limits_truncate_stdout() -> None:
    session = await FakeExecutor().open_session("r", 0)
    result = await session.run(
        Command(argv=("nasm", "--version")), ExecLimits(timeout=5.0, max_stdout_bytes=4)
    )
    assert result.returncode == 0
    assert len(result.stdout) == 4


async def test_limits_truncate_stderr() -> None:
    override = ExecResult(returncode=1, stdout=b"", stderr=b"error message here", elapsed=0.0)
    session = await FakeExecutor(responses={("bad",): override}).open_session("r", 0)
    result = await session.run(Command(argv=("bad",)), ExecLimits(max_stderr_bytes=5))
    assert result.stderr == b"error"
