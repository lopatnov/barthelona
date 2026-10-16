"""Unit tests for the WSL agent allow-list and sandbox enforcement.

These run without WSL or Docker: they import and call the agent functions
directly in Python.
"""

from __future__ import annotations

from pathlib import Path

from barthelona.executors import _wsl_agent as agent  # agent module lives in the package

# ---------------------------------------------------------------------------
# _is_allowed
# ---------------------------------------------------------------------------


def test_docker_exec_bartc_allowed() -> None:
    assert agent._is_allowed(["docker", "exec", "bart-tc", "nasm", "--version"])


def test_docker_run_bart_run_allowed() -> None:
    assert agent._is_allowed(["docker", "run", "bart-run", "echo", "hi"])


def test_docker_run_wrong_image_rejected() -> None:
    assert not agent._is_allowed(["docker", "run", "ubuntu", "bash"])


def test_docker_exec_wrong_container_rejected() -> None:
    assert not agent._is_allowed(["docker", "exec", "other-container", "ls"])


def test_tar_allowed() -> None:
    assert agent._is_allowed(["tar", "-cf", "-", "."])


def test_sha256sum_allowed() -> None:
    assert agent._is_allowed(["sha256sum", "file.bin"])


def test_unknown_command_rejected() -> None:
    assert not agent._is_allowed(["bash", "-c", "echo hi"])


def test_empty_argv_rejected() -> None:
    assert not agent._is_allowed([])


# ---------------------------------------------------------------------------
# _build_docker_run_argv — sandbox flags are injected by agent
# ---------------------------------------------------------------------------


def test_build_docker_run_injects_sandbox_flags() -> None:
    result = agent._build_docker_run_argv(["docker", "run", "bart-run", "echo", "ok"])
    assert result is not None
    assert "--network" in result
    assert "none" in result
    assert "--read-only" in result
    assert "--cap-drop" in result
    assert "ALL" in result
    assert "--rm" in result
    assert "bart-run" in result
    assert result[-2:] == ["echo", "ok"]


def test_build_docker_run_rejects_caller_flags() -> None:
    # Caller must not pass docker flags; agent injects them.
    result = agent._build_docker_run_argv(["docker", "run", "--privileged", "bart-run"])
    assert result is None


def test_build_docker_run_rejects_wrong_image() -> None:
    result = agent._build_docker_run_argv(["docker", "run", "ubuntu", "bash"])
    assert result is None


def test_build_docker_run_rejects_too_short() -> None:
    result = agent._build_docker_run_argv(["docker", "run"])
    assert result is None


# ---------------------------------------------------------------------------
# _handle — full request handling
# ---------------------------------------------------------------------------


def test_handle_empty_cmd_returns_error() -> None:
    result = agent._handle({"cmd": []})
    assert result["returncode"] == 1


def test_handle_disallowed_command_returns_error() -> None:
    result = agent._handle({"cmd": ["bash", "-c", "id"]})
    assert result["returncode"] == 1
    assert "allow-list" in str(result["stderr"])


def test_handle_docker_run_with_flags_rejected() -> None:
    result = agent._handle({"cmd": ["docker", "run", "--privileged", "bart-run"]})
    assert result["returncode"] == 1


def test_handle_cwd_outside_cache_rejected(tmp_path: Path) -> None:
    result = agent._handle({"cmd": ["tar", "-cf", "-", "."], "cwd": str(tmp_path)})
    assert result["returncode"] == 1
    assert "cache root" in str(result["stderr"])


def test_handle_tar_c_outside_cache_rejected() -> None:
    result = agent._handle({"cmd": ["tar", "-xf", "-", "-C", "/tmp/evil"]})
    assert result["returncode"] == 1


# ---------------------------------------------------------------------------
# _is_safe_path
# ---------------------------------------------------------------------------


def test_is_safe_path_cache_root_subdir() -> None:
    import os

    cache = os.path.expanduser("~/.cache/barthelona/runs/x/1")
    assert agent._is_safe_path(cache)


def test_is_safe_path_outside_returns_false(tmp_path: Path) -> None:
    assert not agent._is_safe_path(str(tmp_path))


def test_is_safe_path_home_dir_returns_false() -> None:
    assert not agent._is_safe_path("~")


# ---------------------------------------------------------------------------
# _validate_tar_paths
# ---------------------------------------------------------------------------


def test_validate_tar_paths_safe_c_dir() -> None:
    import os

    safe = os.path.expanduser("~/.cache/barthelona/work")
    assert agent._validate_tar_paths(["-xf", "-", "-C", safe])


def test_validate_tar_paths_unsafe_c_dir() -> None:
    assert not agent._validate_tar_paths(["-xf", "-", "-C", "/etc"])


def test_validate_tar_paths_no_c_is_ok() -> None:
    # No -C means tar uses cwd (checked separately); passes here.
    assert agent._validate_tar_paths(["-cf", "-", "."])
