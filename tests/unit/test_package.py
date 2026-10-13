"""Baseline checks that hold before any feature code exists."""

import subprocess
import sys
import tomllib
from pathlib import Path

import barthelona

ROOT = Path(__file__).resolve().parents[2]


def test_version_matches_pyproject() -> None:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert barthelona.__version__ == meta["project"]["version"]


def test_python_dependencies_are_locked_for_both_platforms() -> None:
    for name in ("runtime.win.lock", "dev.win.lock", "runtime.linux.lock", "dev.linux.lock"):
        lock = ROOT / "requirements" / name
        assert lock.is_file(), f"missing {lock}; run scripts/lock.ps1"
        assert "--hash=sha256:" in lock.read_text(encoding="utf-8")


def test_locks_match_pyproject_dependencies() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "deps_fingerprint.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "Run scripts/lock.ps1 and commit the updated locks."


def test_codex_mirror_matches_claude_config() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_agent_configs.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
