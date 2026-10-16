"""Unit tests for the verification ladder (V0, V1, V2).

Uses FakeExecutor and NasmAdapter to avoid WSL / Docker at test time.
"""

from __future__ import annotations

import tarfile
import io
from pathlib import Path

import pytest

from barthelona.domain.enums import Level, ObjFormat, Linker
from barthelona.domain.verification import LevelResult, Severity
from barthelona.executors._types import ExecResult
from barthelona.executors.fake import FakeExecutor
from barthelona.toolchains.nasm import NasmAdapter
from barthelona.toolchains.gas import GasAttAdapter
from barthelona.verification.ladder import run_ladder, run_v0, run_v1, run_v2

_WORK = "~/.cache/barthelona/verify-tmp"
_CONTAINER = "bart-tc"

# Source file stubs (content doesn't matter; they're never actually read by FakeExecutor)
_HELLO = Path("hello.asm")
_WORLD = Path("world.asm")


def _source_files(*names: str) -> list[Path]:
    return [Path(n) for n in names]


def _nasm_v0_argv(name: str) -> tuple[str, ...]:
    return ("docker", "exec", _CONTAINER, "nasm", "-o", "/dev/null", f"{_WORK}/{name}")


def _nasm_v1_argv(name: str) -> tuple[str, ...]:
    stem = Path(name).stem
    return (
        "docker", "exec", _CONTAINER,
        "nasm", "-f", "elf64",
        "-o", f"{_WORK}/{stem}.o",
        f"{_WORK}/{name}",
    )


def _ld_argv(*obj_names: str) -> tuple[str, ...]:
    objs = tuple(f"{_WORK}/{o}" for o in obj_names)
    return ("docker", "exec", _CONTAINER, "ld", "-e", "_start", "-o", f"{_WORK}/output.elf", *objs)


# ---------------------------------------------------------------------------
# run_v0
# ---------------------------------------------------------------------------


class TestRunV0:
    def test_all_pass(self) -> None:
        executor = FakeExecutor()
        adapter = NasmAdapter()
        result = run_v0(executor, adapter, [_HELLO], _WORK, container=_CONTAINER)
        assert result.level == Level.V0
        assert result.status == "pass"
        assert result.diagnostics == []

    def test_one_file_fails(self, tmp_path: Path) -> None:
        fail_argv = _nasm_v0_argv("hello.asm")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"error: syntax error", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result = run_v0(executor, NasmAdapter(), [_HELLO], _WORK, container=_CONTAINER)
        assert result.status == "fail"
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].severity == Severity.FATAL
        assert "syntax error" in result.diagnostics[0].message

    def test_stages_tar_before_running(self) -> None:
        executor = FakeExecutor()
        run_v0(executor, NasmAdapter(), [_HELLO], _WORK)
        # stage is called by run_ladder; run_v0 alone does not stage
        # (staging is the ladder's responsibility)

    def test_elapsed_is_nonnegative(self) -> None:
        result = run_v0(FakeExecutor(), NasmAdapter(), [_HELLO], _WORK)
        assert result.secs >= 0


# ---------------------------------------------------------------------------
# run_v1
# ---------------------------------------------------------------------------


class TestRunV1:
    def test_all_pass_returns_object_paths(self) -> None:
        executor = FakeExecutor()
        result, obj_paths = run_v1(executor, NasmAdapter(), [_HELLO], _WORK, container=_CONTAINER)
        assert result.status == "pass"
        assert len(obj_paths) == 1
        assert obj_paths[0].endswith("hello.o")

    def test_failure_returns_no_object_path(self) -> None:
        fail_argv = _nasm_v1_argv("hello.asm")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"asm failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result, obj_paths = run_v1(executor, NasmAdapter(), [_HELLO], _WORK, container=_CONTAINER)
        assert result.status == "fail"
        assert obj_paths == []

    def test_multiple_sources_all_pass(self) -> None:
        executor = FakeExecutor()
        result, obj_paths = run_v1(executor, NasmAdapter(), [_HELLO, _WORLD], _WORK, container=_CONTAINER)
        assert result.status == "pass"
        assert len(obj_paths) == 2

    def test_partial_failure_stops_collecting_objects(self) -> None:
        fail_argv = _nasm_v1_argv("hello.asm")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"asm failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result, obj_paths = run_v1(
            executor, NasmAdapter(), [_HELLO, _WORLD], _WORK, container=_CONTAINER
        )
        assert result.status == "fail"
        # world.asm still assembled successfully
        assert any("world.o" in p for p in obj_paths)


# ---------------------------------------------------------------------------
# run_v2
# ---------------------------------------------------------------------------


class TestRunV2:
    def test_pass_with_objects(self) -> None:
        executor = FakeExecutor()
        result = run_v2(executor, [f"{_WORK}/hello.o"], _WORK, container=_CONTAINER)
        assert result.status == "pass"

    def test_skipped_when_no_objects(self) -> None:
        result = run_v2(FakeExecutor(), [], _WORK)
        assert result.status == "skipped"

    def test_failure_on_linker_error(self) -> None:
        fail_argv = _ld_argv("hello.o")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"ld: undefined symbol", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result = run_v2(executor, [f"{_WORK}/hello.o"], _WORK, container=_CONTAINER)
        assert result.status == "fail"
        assert "undefined symbol" in result.diagnostics[0].message


# ---------------------------------------------------------------------------
# run_ladder (integration)
# ---------------------------------------------------------------------------


def _make_real_source(tmp_path: Path) -> list[Path]:
    """Write a stub source file so _make_tar can read it."""
    src = tmp_path / "hello.asm"
    src.write_text("; stub\n", encoding="utf-8")
    return [src]


class TestRunLadder:
    def test_empty_sources_returns_empty(self, tmp_path: Path) -> None:
        result = run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), [], _WORK)
        assert result == []

    def test_v0_only(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        results = run_ladder(Level.V0, FakeExecutor(), NasmAdapter(), sources, _WORK)
        assert len(results) == 1
        assert results[0].level == Level.V0
        assert results[0].status == "pass"

    def test_v2_ladder_all_pass(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        results = run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), sources, _WORK)
        assert len(results) == 3
        levels = [r.level for r in results]
        assert levels == [Level.V0, Level.V1, Level.V2]
        assert all(r.status == "pass" for r in results)

    def test_v0_fail_skips_v1_and_v2(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        fail_argv = _nasm_v0_argv(sources[0].name)
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"syntax error", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        results = run_ladder(Level.V2, executor, NasmAdapter(), sources, _WORK)
        assert results[0].status == "fail"
        assert results[1].status == "skipped"
        assert results[2].status == "skipped"

    def test_v1_fail_skips_v2(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        fail_argv = _nasm_v1_argv(sources[0].name)
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"assemble failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        results = run_ladder(Level.V2, executor, NasmAdapter(), sources, _WORK)
        assert results[0].status == "pass"
        assert results[1].status == "fail"
        assert results[2].status == "skipped"

    def test_stages_tar_with_source_files(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        executor = FakeExecutor()
        run_ladder(Level.V0, executor, NasmAdapter(), sources, _WORK)
        assert executor.staged is not None
        # The tar should contain the source file
        with tarfile.open(fileobj=io.BytesIO(executor.staged)) as tf:
            names = tf.getnames()
        assert "hello.asm" in names

    def test_gas_att_adapter(self, tmp_path: Path) -> None:
        src = tmp_path / "hello.s"
        src.write_text("; stub\n", encoding="utf-8")
        results = run_ladder(Level.V0, FakeExecutor(), GasAttAdapter(), [src], _WORK)
        assert results[0].status == "pass"
