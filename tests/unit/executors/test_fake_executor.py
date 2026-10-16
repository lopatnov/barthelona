"""Unit tests for FakeExecutor (no WSL or Docker required)."""

from __future__ import annotations

from barthelona.executors import Command, ExecLimits, ExecResult, FakeExecutor


def test_executor_id_default() -> None:
    exc = FakeExecutor()
    assert exc.executor_id == "tc"


def test_executor_id_custom() -> None:
    exc = FakeExecutor(executor_id="sandbox")
    assert exc.executor_id == "sandbox"


def test_may_run_untrusted_default() -> None:
    exc = FakeExecutor()
    assert exc.may_run_untrusted is False


def test_probe_returns_tool_names() -> None:
    exc = FakeExecutor()
    tools = exc.probe()
    assert "nasm" in tools
    assert "gcc" in tools
    assert tools["nasm"].startswith("NASM")


def test_version_command_auto() -> None:
    exc = FakeExecutor()
    result = exc.run(Command(argv=("nasm", "--version")))
    assert result.returncode == 0
    assert b"NASM" in result.stdout


def test_which_command_auto() -> None:
    exc = FakeExecutor()
    result = exc.run(Command(argv=("which", "nasm")))
    assert result.returncode == 0
    assert b"/usr/bin/nasm" in result.stdout


def test_docker_inspect_auto() -> None:
    exc = FakeExecutor(image_digest="sha256:abc123")
    result = exc.run(
        Command(argv=("docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-tc"))
    )
    assert result.returncode == 0
    assert b"sha256:abc123" in result.stdout


def test_explicit_response_override() -> None:
    override = ExecResult(returncode=42, stdout=b"custom", stderr=b"", elapsed=0.0)
    exc = FakeExecutor(responses={("echo", "hi"): override})
    result = exc.run(Command(argv=("echo", "hi")))
    assert result.returncode == 42
    assert result.stdout == b"custom"


def test_unknown_command_returns_zero() -> None:
    exc = FakeExecutor()
    result = exc.run(Command(argv=("unknown-binary",)))
    assert result.returncode == 0
    assert result.stdout == b""


def test_stage_stores_bytes() -> None:
    exc = FakeExecutor()
    assert exc.staged is None
    exc.stage(b"archive-content")
    assert exc.staged == b"archive-content"


def test_collect_returns_empty_bytes() -> None:
    exc = FakeExecutor()
    assert exc.collect() == b""


def test_custom_tools_override_defaults() -> None:
    exc = FakeExecutor(tools={"nasm": "NASM version 2.99"})
    tools = exc.probe()
    assert tools == {"nasm": "NASM version 2.99"}
    result = exc.run(Command(argv=("nasm", "--version")))
    assert b"2.99" in result.stdout


def test_limits_unused_on_fake() -> None:
    exc = FakeExecutor()
    lim = ExecLimits(timeout=5.0, max_stdout_bytes=10)
    result = exc.run(Command(argv=("nasm", "--version")), lim)
    # FakeExecutor does not truncate; limits are accepted without error.
    assert result.returncode == 0
