"""Unit tests for the WSL agent allow-list and sandbox enforcement.

These run without WSL or Docker: they import and call the agent functions
directly in Python.
"""

from __future__ import annotations

import sys
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


def test_docker_inspect_allowed() -> None:
    assert agent._is_allowed(["docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-tc"])


def test_docker_inspect_run_image_allowed() -> None:
    assert agent._is_allowed(["docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-run"])


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
# _validate_docker_inspect_argv
# ---------------------------------------------------------------------------


def test_docker_inspect_bartc_allowed() -> None:
    assert agent._validate_docker_inspect_argv(["docker", "inspect", "--format", "{{x}}", "bart-tc"])


def test_docker_inspect_bart_run_allowed() -> None:
    assert agent._validate_docker_inspect_argv(["docker", "inspect", "--format", "{{x}}", "bart-run"])


def test_docker_inspect_arbitrary_image_rejected() -> None:
    assert not agent._validate_docker_inspect_argv(["docker", "inspect", "--format", "{{x}}", "ubuntu"])


def test_docker_inspect_multi_target_rejected() -> None:
    # Multi-target: appending an allowed name must not allow the other target.
    argv = ["docker", "inspect", "--format", "{{x}}", "ubuntu", "bart-tc"]
    assert not agent._validate_docker_inspect_argv(argv)


def test_handle_docker_inspect_bartc_returns_success_format() -> None:
    result = agent._handle({"cmd": ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", "bart-tc"]})
    # On a system without Docker this returns non-zero, but must not be rejected by the agent itself
    assert "allow-list" not in str(result.get("stderr", ""))


def test_handle_docker_inspect_arbitrary_image_rejected() -> None:
    result = agent._handle({"cmd": ["docker", "inspect", "--format", "{{x}}", "ubuntu"]})
    assert result["returncode"] == 1
    assert "bart-tc" in str(result["stderr"])


# ---------------------------------------------------------------------------
# _validate_sha256sum_argv
# ---------------------------------------------------------------------------


def test_validate_sha256sum_relative_path_ok() -> None:
    assert agent._validate_sha256sum_argv(["sha256sum", "file.bin"])


def test_validate_sha256sum_cache_root_ok() -> None:
    import os

    safe = os.path.expanduser("~/.cache/barthelona/work/file.bin")
    assert agent._validate_sha256sum_argv(["sha256sum", safe])


def test_validate_sha256sum_outside_cache_rejected() -> None:
    assert not agent._validate_sha256sum_argv(["sha256sum", "/etc/passwd"])


def test_validate_sha256sum_flag_skipped() -> None:
    assert agent._validate_sha256sum_argv(["sha256sum", "--check", "-"])


def test_handle_sha256sum_outside_cache_rejected() -> None:
    result = agent._handle({"cmd": ["sha256sum", "/etc/passwd"]})
    assert result["returncode"] == 1
    assert "cache root" in str(result["stderr"])


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


# ---------------------------------------------------------------------------
# sandbox mount, ulimits and the path-fence prefix fix (#77)
# ---------------------------------------------------------------------------


def test_sandbox_flags_include_ulimits() -> None:
    result = agent._build_docker_run_argv(["docker", "run", "bart-run", "true"])
    assert result is not None
    assert result.count("--ulimit") == 2
    assert "nofile=64" in result
    assert "fsize=16777216" in result


def test_mount_becomes_read_only_work_volume() -> None:
    mount = f"{agent._CACHE_ROOT}/runs/r/0"
    result = agent._build_docker_run_argv(["docker", "run", "bart-run", "/work/out"], mount)
    assert result is not None
    volume = result.index("-v")
    assert result[volume + 1] == f"{mount}:/work:ro"
    assert volume < result.index("bart-run")


def test_mount_inside_cache_root_is_accepted() -> None:
    argv = ["docker", "run", "bart-run", "true"]
    assert agent._validate_request(argv, None, f"{agent._CACHE_ROOT}/runs/r/0") is None


def test_mount_outside_cache_root_is_rejected(tmp_path: Path) -> None:
    argv = ["docker", "run", "bart-run", "true"]
    error = agent._validate_request(argv, None, str(tmp_path))
    assert error is not None
    assert "mount outside cache root" in error


def test_mount_with_volume_syntax_is_rejected() -> None:
    argv = ["docker", "run", "bart-run", "true"]
    assert agent._validate_request(argv, None, f"{agent._CACHE_ROOT}/x:/etc:rw") is not None


def test_mount_is_rejected_for_other_commands() -> None:
    argv = ["docker", "exec", "bart-tc", "nasm"]
    error = agent._validate_request(argv, None, f"{agent._CACHE_ROOT}/runs/r/0")
    assert error is not None
    assert "docker run" in error


def test_handle_rejects_mount_outside_cache_root(tmp_path: Path) -> None:
    result = agent._handle({"cmd": ["docker", "run", "bart-run", "true"], "mount": str(tmp_path)})
    assert result["rejected"] is True


def test_sibling_directory_with_cache_root_prefix_is_unsafe() -> None:
    assert not agent._is_safe_path(agent._CACHE_ROOT + "-evil")
    assert agent._is_safe_path(agent._CACHE_ROOT)


def test_mount_must_be_absolute_and_free_of_tilde() -> None:
    argv = ["docker", "run", "bart-run", "true"]
    assert agent._validate_request(argv, None, "runs/r/0") is not None  # would become a named volume
    assert agent._validate_request(argv, None, "~/.cache/barthelona/runs/r/0") is not None


def test_mount_must_be_under_runs() -> None:
    argv = ["docker", "run", "bart-run", "true"]
    assert agent._validate_request(argv, None, agent._CACHE_ROOT) is not None
    assert agent._validate_request(argv, None, f"{agent._CACHE_ROOT}/other") is not None


def test_mount_symlink_escaping_the_cache_root_is_rejected(tmp_path: Path) -> None:
    # Windows requires admin privileges for symlinks; skip if not available
    if sys.platform == "win32":
        import pytest

        pytest.skip("symlink creation requires admin on Windows")
    runs = Path(agent._CACHE_ROOT) / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    link = runs / "symlink-escape-test"
    link.symlink_to(tmp_path)
    try:
        assert agent._resolve_mount(str(link)) is None
    finally:
        link.unlink()


def test_resolved_mount_is_what_docker_receives() -> None:
    mount = f"{agent._CACHE_ROOT}/runs/r/../r/0"
    assert agent._resolve_mount(mount) == f"{agent._CACHE_ROOT}/runs/r/0"


def test_mount_under_runs_cannot_carry_extra_volume_fields() -> None:
    argv = ["docker", "run", "bart-run", "true"]
    for mount in (f"{agent._CACHE_ROOT}/runs/x:/work:rw", f"{agent._CACHE_ROOT}/runs/x:rw"):
        assert agent._validate_request(argv, None, mount) is not None
