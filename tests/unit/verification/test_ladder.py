"""Unit tests for the verification ladder (V0, V1, V2).

Uses FakeExecutor and NasmAdapter to avoid WSL / Docker at test time.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from barthelona.domain.enums import Level
from barthelona.domain.verification import LevelResult, Severity
from barthelona.executors._types import ExecResult
from barthelona.executors.fake import FakeExecutor
from barthelona.executors.protocol import Session
from barthelona.toolchains.gas import GasAttAdapter
from barthelona.toolchains.nasm import NasmAdapter
from barthelona.verification.ladder import dod_satisfied, run_ladder
from barthelona.verification.native_asm import run_v0, run_v1, run_v2
from barthelona.verification.registry import CheckRegistry, LadderContext, Unsupported

_RUN = "t"
_WORK = f"/fake/work/{_RUN}/0"  # FakeExecutor session directory for (run, attempt 0)

# Source file stubs (content doesn't matter; they're never actually read by FakeExecutor)
_HELLO = Path("hello.asm")
_WORLD = Path("world.asm")


async def _session(executor: FakeExecutor | None = None) -> Session:
    return await (executor or FakeExecutor()).open_session(_RUN, 0)


def _source_files(*names: str) -> list[Path]:
    return [Path(n) for n in names]


def _nasm_v0_argv(name: str) -> tuple[str, ...]:
    return ("nasm", "-o", "/dev/null", f"{_WORK}/{name}")


def _nasm_v1_argv(name: str) -> tuple[str, ...]:
    stem = Path(name).stem
    return (
        "nasm",
        "-f",
        "elf64",
        "-o",
        f"{_WORK}/{stem}.o",
        f"{_WORK}/{name}",
    )


def _ld_argv(*obj_names: str) -> tuple[str, ...]:
    objs = tuple(f"{_WORK}/{o}" for o in obj_names)
    return ("ld", "-e", "_start", "-o", f"{_WORK}/output.elf", *objs)


# ---------------------------------------------------------------------------
# run_v0
# ---------------------------------------------------------------------------


class TestRunV0:
    async def test_all_pass(self) -> None:
        executor = FakeExecutor()
        adapter = NasmAdapter()
        result = await run_v0(await _session(executor), adapter, [_HELLO])
        assert result.level == Level.V0
        assert result.status == "pass"
        assert result.diagnostics == []

    async def test_one_file_fails(self, tmp_path: Path) -> None:
        fail_argv = _nasm_v0_argv("hello.asm")
        responses = {
            fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"error: syntax error", elapsed=0.0)
        }
        executor = FakeExecutor(responses=responses)
        result = await run_v0(await _session(executor), NasmAdapter(), [_HELLO])
        assert result.status == "fail"
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].severity == Severity.FATAL
        assert "syntax error" in result.diagnostics[0].message

    async def test_elapsed_is_nonnegative(self) -> None:
        result = await run_v0(await _session(), NasmAdapter(), [_HELLO])
        assert result.secs >= 0


# ---------------------------------------------------------------------------
# run_v1
# ---------------------------------------------------------------------------


class TestRunV1:
    async def test_all_pass_returns_object_paths(self) -> None:
        executor = FakeExecutor()
        result, obj_paths = await run_v1(await _session(executor), NasmAdapter(), [_HELLO])
        assert result.status == "pass"
        assert len(obj_paths) == 1
        assert obj_paths[0].endswith("hello.o")

    async def test_failure_returns_no_object_path(self) -> None:
        fail_argv = _nasm_v1_argv("hello.asm")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"asm failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result, obj_paths = await run_v1(await _session(executor), NasmAdapter(), [_HELLO])
        assert result.status == "fail"
        assert obj_paths == []

    async def test_multiple_sources_all_pass(self) -> None:
        executor = FakeExecutor()
        result, obj_paths = await run_v1(await _session(executor), NasmAdapter(), [_HELLO, _WORLD])
        assert result.status == "pass"
        assert len(obj_paths) == 2

    async def test_partial_failure_stops_collecting_objects(self) -> None:
        fail_argv = _nasm_v1_argv("hello.asm")
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"asm failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        result, obj_paths = await run_v1(await _session(executor), NasmAdapter(), [_HELLO, _WORLD])
        assert result.status == "fail"
        # world.asm still assembled successfully
        assert any("world.o" in p for p in obj_paths)


# ---------------------------------------------------------------------------
# run_v2
# ---------------------------------------------------------------------------


class TestRunV2:
    async def test_pass_with_objects(self) -> None:
        executor = FakeExecutor()
        result = await run_v2(await _session(executor), [f"{_WORK}/hello.o"])
        assert result.status == "pass"

    async def test_skipped_when_no_objects(self) -> None:
        result = await run_v2(await _session(), [])
        assert result.status == "skipped"

    async def test_failure_on_linker_error(self) -> None:
        fail_argv = _ld_argv("hello.o")
        responses = {
            fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"ld: undefined symbol", elapsed=0.0)
        }
        executor = FakeExecutor(responses=responses)
        result = await run_v2(await _session(executor), [f"{_WORK}/hello.o"])
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
    async def test_empty_sources_returns_empty(self, tmp_path: Path) -> None:
        result = await run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), [], _RUN)
        assert result == []

    async def test_v0_only(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        results = await run_ladder(Level.V0, FakeExecutor(), NasmAdapter(), sources, _RUN)
        assert len(results) == 1
        assert results[0].level == Level.V0
        assert results[0].status == "pass"

    async def test_v2_ladder_all_pass(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        results = await run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), sources, _RUN)
        assert len(results) == 3
        levels = [r.level for r in results]
        assert levels == [Level.V0, Level.V1, Level.V2]
        assert all(r.status == "pass" for r in results)

    async def test_v0_fail_skips_v1_and_v2(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        fail_argv = _nasm_v0_argv(sources[0].name)
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"syntax error", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        results = await run_ladder(Level.V2, executor, NasmAdapter(), sources, _RUN)
        assert results[0].status == "fail"
        assert results[1].status == "skipped"
        assert results[2].status == "skipped"

    async def test_v1_fail_skips_v2(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        fail_argv = _nasm_v1_argv(sources[0].name)
        responses = {fail_argv: ExecResult(returncode=1, stdout=b"", stderr=b"assemble failed", elapsed=0.0)}
        executor = FakeExecutor(responses=responses)
        results = await run_ladder(Level.V2, executor, NasmAdapter(), sources, _RUN)
        assert results[0].status == "pass"
        assert results[1].status == "fail"
        assert results[2].status == "skipped"

    async def test_stages_tar_with_source_files(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        executor = FakeExecutor()
        await run_ladder(Level.V0, executor, NasmAdapter(), sources, _RUN)
        assert executor.staged is not None
        # The tar should contain the source file
        with tarfile.open(fileobj=io.BytesIO(executor.staged)) as tf:
            names = tf.getnames()
        assert "hello.asm" in names

    async def test_gas_att_adapter(self, tmp_path: Path) -> None:
        src = tmp_path / "hello.s"
        src.write_text("; stub\n", encoding="utf-8")
        results = await run_ladder(Level.V0, FakeExecutor(), GasAttAdapter(), [src], _RUN)
        assert results[0].status == "pass"


# ---------------------------------------------------------------------------
# registry behaviour (D-046)
# ---------------------------------------------------------------------------


class _StubCheck:
    always_run = False

    def __init__(self, level: Level, status: str = "pass", unsupported: str | None = None) -> None:
        self.level = level
        self._status = status
        self._unsupported = unsupported
        self.ran = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        return Unsupported(self._unsupported) if self._unsupported else None

    async def run(self, ctx: LadderContext) -> LevelResult:
        self.ran = True
        return LevelResult(level=self.level, status=self._status, secs=0.0)  # type: ignore[arg-type]  # test stub passes a valid literal


def _registry(*checks: _StubCheck) -> CheckRegistry:
    registry = CheckRegistry()
    for check in checks:
        registry.register("native-asm", check)
    return registry


class TestRegistry:
    async def test_level_without_check_is_unsupported(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        registry = _registry(_StubCheck(Level.V0))
        results = await run_ladder(Level.V1, FakeExecutor(), NasmAdapter(), sources, _RUN, registry=registry)
        assert [r.status for r in results] == ["pass", "unsupported"]

    async def test_unsupported_check_does_not_run_and_does_not_stop_the_walk(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        v1 = _StubCheck(Level.V1, unsupported="no such thing")
        v2 = _StubCheck(Level.V2)
        registry = _registry(_StubCheck(Level.V0), v1, v2)
        results = await run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), sources, _RUN, registry=registry)
        assert [r.status for r in results] == ["pass", "unsupported", "pass"]
        assert results[1].diagnostics[0].message == "no such thing"
        assert not v1.ran
        assert v2.ran

    async def test_always_run_check_runs_after_failure_but_does_not_clear_it(self, tmp_path: Path) -> None:
        sources = _make_real_source(tmp_path)
        trace = _StubCheck(Level.V1)
        trace.always_run = True
        registry = _registry(_StubCheck(Level.V0, status="fail"), trace, _StubCheck(Level.V2))
        results = await run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), sources, _RUN, registry=registry)
        assert [r.status for r in results] == ["fail", "pass", "skipped"]
        assert not dod_satisfied(Level.V2, results)

    async def test_duplicate_registration_is_rejected(self) -> None:
        registry = _registry(_StubCheck(Level.V0))
        try:
            registry.register("native-asm", _StubCheck(Level.V0))
        except ValueError as exc:
            assert "V0" in str(exc)
        else:
            raise AssertionError("duplicate registration was accepted")


class TestDodSatisfied:
    async def test_all_levels_passed(self, tmp_path: Path) -> None:
        results = await run_ladder(Level.V2, FakeExecutor(), NasmAdapter(), _make_real_source(tmp_path), _RUN)
        assert dod_satisfied(Level.V2, results)

    async def test_unsupported_required_level_is_not_done(self, tmp_path: Path) -> None:
        results = await run_ladder(Level.V3, FakeExecutor(), NasmAdapter(), _make_real_source(tmp_path), _RUN)
        assert results[-1].status == "unsupported"
        assert not dod_satisfied(Level.V3, results)
        assert dod_satisfied(Level.V2, results)

    def test_missing_level_is_not_done(self) -> None:
        assert not dod_satisfied(Level.V1, [LevelResult(level=Level.V0, status="pass", secs=0.0)])
