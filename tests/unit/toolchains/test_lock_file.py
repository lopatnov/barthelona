"""Unit tests for write_lock_file / read_lock_file round-trip."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from barthelona.toolchains import ToolchainLock, ToolInfo, read_lock_file, write_lock_file


def _make_lock() -> ToolchainLock:
    return ToolchainLock(
        toolchain_image_digest="sha256:abc",
        runner_image_digest="sha256:def",
        tools={
            "nasm": ToolInfo(version="NASM version 2.16.03", path="/usr/bin/nasm"),
            "as": ToolInfo(version="GNU assembler 2.42", path="/usr/bin/as"),
        },
        probed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def test_write_creates_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "config" / "toolchains.lock.json"
    write_lock_file(_make_lock(), lock_path)
    assert lock_path.exists()


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    lock_path = tmp_path / "deeply" / "nested" / "toolchains.lock.json"
    write_lock_file(_make_lock(), lock_path)
    assert lock_path.exists()


def test_write_produces_valid_json(tmp_path: Path) -> None:
    lock_path = tmp_path / "toolchains.lock.json"
    write_lock_file(_make_lock(), lock_path)
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["toolchain_image_digest"] == "sha256:abc"
    assert "nasm" in data["tools"]


def test_write_ends_with_newline(tmp_path: Path) -> None:
    lock_path = tmp_path / "toolchains.lock.json"
    write_lock_file(_make_lock(), lock_path)
    raw = lock_path.read_bytes()
    assert raw.endswith(b"\n")


def test_roundtrip(tmp_path: Path) -> None:
    lock_path = tmp_path / "toolchains.lock.json"
    original = _make_lock()
    write_lock_file(original, lock_path)
    loaded = read_lock_file(lock_path)
    assert loaded.toolchain_image_digest == original.toolchain_image_digest
    assert loaded.runner_image_digest == original.runner_image_digest
    assert loaded.tools["nasm"].version == original.tools["nasm"].version
    assert loaded.tools["nasm"].path == original.tools["nasm"].path
    assert loaded.probed_at == original.probed_at


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_lock_file(tmp_path / "nonexistent.json")


def test_read_invalid_json_raises(tmp_path: Path) -> None:
    lock_path = tmp_path / "toolchains.lock.json"
    lock_path.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_lock_file(lock_path)


def test_read_invalid_schema_raises(tmp_path: Path) -> None:
    """Missing required fields raises ValidationError."""
    from pydantic import ValidationError

    lock_path = tmp_path / "toolchains.lock.json"
    lock_path.write_text(json.dumps({"not": "a valid lock"}), encoding="utf-8")
    with pytest.raises(ValidationError):
        read_lock_file(lock_path)
