"""Unit tests for toolchain probe logic (no WSL or Docker required)."""

from __future__ import annotations

from barthelona.executors import Command, ExecResult, FakeExecutor
from barthelona.toolchains import ToolInfo, probe_image_digest, probe_tools, run_probe


def _fake_exec(image_digest: str = "sha256:tc000") -> FakeExecutor:
    """FakeExecutor wired with docker-exec wrappers for probe_tools."""
    # probe_tools sends `docker exec bart-tc <tool> --version`
    # and `docker exec bart-tc which <tool>`.
    def _docker_version(tool: str, version_line: str) -> tuple[tuple[str, ...], ExecResult]:
        argv = ("docker", "exec", "bart-tc", tool, "--version")
        return argv, ExecResult(returncode=0, stdout=(version_line + "\n").encode(), stderr=b"", elapsed=0.001)

    def _docker_which(tool: str, path: str) -> tuple[tuple[str, ...], ExecResult]:
        argv = ("docker", "exec", "bart-tc", "which", tool)
        return argv, ExecResult(returncode=0, stdout=(path + "\n").encode(), stderr=b"", elapsed=0.001)

    responses: dict[tuple[str, ...], ExecResult] = {}
    tool_data = {
        "nasm": ("NASM version 2.16.03", "/usr/bin/nasm"),
        "as": ("GNU assembler 2.42", "/usr/bin/as"),
        "ld": ("GNU ld 2.42", "/usr/bin/ld"),
        "gcc": ("gcc 15.2.0", "/usr/bin/gcc"),
        "nm": ("GNU nm 2.42", "/usr/bin/nm"),
        "make": ("GNU Make 4.4.1", "/usr/bin/make"),
        "gdb": ("GNU gdb 16.1", "/usr/bin/gdb"),
    }
    for tool, (ver, path) in tool_data.items():
        k, v = _docker_version(tool, ver)
        responses[k] = v
        k, v = _docker_which(tool, path)
        responses[k] = v

    # docker inspect for digest
    inspect_argv = ("docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-tc")
    responses[inspect_argv] = ExecResult(
        returncode=0, stdout=(image_digest + "\n").encode(), stderr=b"", elapsed=0.001
    )
    run_inspect_argv = ("docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-run")
    responses[run_inspect_argv] = ExecResult(
        returncode=0, stdout=("sha256:run000\n").encode(), stderr=b"", elapsed=0.001
    )

    return FakeExecutor(responses=responses, image_digest=image_digest)


def test_probe_tools_returns_all_standard_tools() -> None:
    exc = _fake_exec()
    tools = probe_tools(exc)
    assert set(tools.keys()) == {"nasm", "as", "ld", "gcc", "nm", "make", "gdb"}


def test_probe_tools_version_content() -> None:
    exc = _fake_exec()
    tools = probe_tools(exc)
    assert tools["nasm"].version == "NASM version 2.16.03"
    assert tools["nasm"].path == "/usr/bin/nasm"


def test_probe_tools_skips_missing_tool() -> None:
    """A tool whose --version fails is omitted from the result."""
    exc = _fake_exec()
    # Override nasm --version to fail.
    exc._responses[("docker", "exec", "bart-tc", "nasm", "--version")] = ExecResult(
        returncode=127, stdout=b"", stderr=b"not found", elapsed=0.001
    )
    tools = probe_tools(exc)
    assert "nasm" not in tools
    assert "as" in tools


def test_probe_image_digest() -> None:
    exc = _fake_exec(image_digest="sha256:tc999")
    digest = probe_image_digest(exc, "bart-tc")
    assert digest == "sha256:tc999"


def test_probe_image_digest_failure() -> None:
    """Returns empty string when docker inspect fails."""
    exc = FakeExecutor(
        responses={
            ("docker", "inspect", "--format", "{{index .RepoDigests 0}}", "missing-img"): ExecResult(
                returncode=1, stdout=b"", stderr=b"No such object", elapsed=0.001
            )
        }
    )
    digest = probe_image_digest(exc, "missing-img")
    assert digest == ""


def test_run_probe_produces_toolchain_lock() -> None:
    exc = _fake_exec()
    lock = run_probe(exc)
    assert lock.toolchain_image_digest == "sha256:tc000"
    assert lock.runner_image_digest == "sha256:run000"
    assert "nasm" in lock.tools
    assert isinstance(lock.tools["nasm"], ToolInfo)
    assert lock.probed_at is not None


def test_run_probe_timestamp_is_utc() -> None:
    from datetime import UTC

    exc = _fake_exec()
    lock = run_probe(exc)
    assert lock.probed_at.tzinfo is not None
    # Should be very close to now; just confirm it parses.
    assert lock.probed_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
