"""The c-gcc arm: arm wiring, the C prompt, the derived GAS Intel task and the compile-failure feedback."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.bench import Arm, BenchTask, RunSettings, TaskRun, load_prompts, load_suite, run_task
from barthelona.bench.c_arm import CGccVerifier, c_source_name, gas_intel_variant, gcc_argv
from barthelona.bench.prompts import render_c_prompt
from barthelona.domain.enums import DiagnosticLevel, Dialect, StopReason
from barthelona.domain.verification import LevelResult
from barthelona.executors import ExecResult, FakeExecutor
from barthelona.llm import FakeGateway

BENCH = Path(__file__).resolve().parents[3] / "bench"
TASK = next(task for task in load_suite(BENCH, "dev") if task.id == "gcd")
GOOD_C = "=== FILE: gcd.c ===\nuint64_t gcd(uint64_t a, uint64_t b) { return a; }\n=== END ==="
ASSEMBLY = '.intel_syntax noprefix\n.globl gcd\ngcd:\n\tret\n.section .note.GNU-stack,"",@progbits\n'
PASS = [
    LevelResult(level=level, status="pass", diagnostics=[], secs=0)  # type: ignore[arg-type]
    for level in ("V0", "V1", "V2", "V5")
]
C_ARM = Arm("c-gcc", 2, language="c")


class _Ladder:
    def __init__(self) -> None:
        self.calls: list[tuple[BenchTask, list[Path]]] = []

    async def verify(
        self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
    ) -> list[LevelResult]:  # NOSONAR S7503
        self.calls.append((task, sources))
        return PASS


def _executor(source: Path, *, stderr: bytes = b"") -> FakeExecutor:
    work = "/fake/work/r-cc/0"
    out = f"{work}/gcd.s"
    ok = stderr == b""
    return FakeExecutor(
        responses={
            gcc_argv(f"{work}/{source.name}", out): ExecResult(0 if ok else 1, b"", stderr, 0.01),
            ("cat", out): ExecResult(0, ASSEMBLY.encode(), b"", 0.01),
        }
    )


def test_gcc_flags_keep_the_output_a_plain_intel_module() -> None:
    argv = gcc_argv("in.c", "out.s")
    assert argv[:4] == ("gcc", "-O2", "-S", "-masm=intel")
    assert {"-fno-asynchronous-unwind-tables", "-fno-pie", "-fcf-protection=none"} <= set(argv)
    assert argv[-3:] == ("-o", "out.s", "in.c")


def test_the_gas_intel_variant_retargets_the_task_without_touching_the_original() -> None:
    variant = gas_intel_variant(TASK)
    assert variant.dialect == Dialect.GAS_INTEL
    assert variant.registry.target.dialect == Dialect.GAS_INTEL
    assert variant.registry.target.preset == "linux-x64-gas-intel"
    assert variant.source_name == "gcd.s"
    assert (TASK.dialect, TASK.source_name) == (Dialect.NASM, "gcd.asm")
    assert variant.tests == TASK.tests


def test_the_c_prompt_shows_a_prototype_and_asks_for_the_c_file() -> None:
    prompt = render_c_prompt(load_prompts(BENCH), TASK, c_source_name(TASK))
    assert "uint64_t gcd(uint64_t a0, uint64_t a1);" in prompt
    assert "=== FILE: gcd.c ===" in prompt
    assert "%include" not in prompt
    assert not any(case.id in prompt for case in TASK.tests)


async def test_a_c_source_is_compiled_and_the_assembly_goes_to_the_ladder_as_gas(tmp_path: Path) -> None:
    source = tmp_path / "gcd.c"
    source.write_text("int x;\n", encoding="utf-8")
    ladder = _Ladder()
    results = await CGccVerifier(_executor(source), ladder).verify(TASK, [source], "r", 0)
    assert results == PASS
    task, sources = ladder.calls[0]
    assert task.dialect == Dialect.GAS_INTEL
    assert [path.name for path in sources] == ["gcd.s"]
    assert sources[0].read_text(encoding="utf-8") == ASSEMBLY


async def test_an_assembly_source_bypasses_gcc(tmp_path: Path) -> None:
    source = tmp_path / "gcd.asm"
    source.write_text("ret\n", encoding="utf-8")
    ladder = _Ladder()
    await CGccVerifier(FakeExecutor(), ladder).verify(TASK, [source], "r", 0)
    assert ladder.calls == [(TASK, [source])]


async def test_a_compile_failure_is_a_failed_v0_with_gcc_diagnostics(tmp_path: Path) -> None:
    source = tmp_path / "gcd.c"
    source.write_text("int x\n", encoding="utf-8")
    stderr = b"gcd.c:1:6: error: expected ';' after top level declarator\n"
    ladder = _Ladder()
    (result,) = await CGccVerifier(_executor(source, stderr=stderr), ladder).verify(TASK, [source], "r", 0)
    assert (result.level, result.status, ladder.calls) == ("V0", "fail", [])
    (diagnostic,) = result.diagnostics
    assert (diagnostic.tool, diagnostic.level, diagnostic.line) == ("gcc", DiagnosticLevel.V0, 1)


async def test_an_unparsable_gcc_failure_still_reports_its_text(tmp_path: Path) -> None:
    source = tmp_path / "gcd.c"
    source.write_text("x\n", encoding="utf-8")
    (result,) = await CGccVerifier(_executor(source, stderr=b"cc1: boom"), _Ladder()).verify(
        TASK, [source], "r", 0
    )
    assert "cc1: boom" in result.diagnostics[0].message


@pytest.mark.parametrize("language", ["asm", "c"])
async def test_the_runner_writes_the_arms_source_file(tmp_path: Path, language: str) -> None:
    written: list[str] = []

    class _Recorder:
        async def verify(
            self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
        ) -> list[LevelResult]:  # NOSONAR S7503
            written.append(sources[0].name)
            return PASS

    reply = GOOD_C if language == "c" else "=== FILE: gcd.asm ===\nret\n=== END ==="
    run = TaskRun(
        TASK, 0, FakeGateway([reply]), _Recorder(), load_prompts(BENCH), "gcd.asm", tmp_path, RunSettings()
    )
    result = await run_task(run, Arm("x", 0, language=language))  # type: ignore[arg-type]
    assert written == ["gcd.c" if language == "c" else "gcd.asm"]
    assert result.stop_reason == StopReason.GREEN


async def test_the_c_arm_fix_loop_feeds_gcc_diagnostics_back(tmp_path: Path) -> None:
    gateway = FakeGateway([GOOD_C, GOOD_C])
    failing = LevelResult(level="V0", status="fail", diagnostics=[], secs=0)  # type: ignore[arg-type]

    class _Scripted:
        def __init__(self) -> None:
            self.outcomes = [[failing], PASS]

        async def verify(
            self, task: BenchTask, sources: list[Path], run_id: str, attempt: int
        ) -> list[LevelResult]:  # NOSONAR S7503
            return self.outcomes.pop(0)

    run = TaskRun(TASK, 0, gateway, _Scripted(), load_prompts(BENCH), "gcd.asm", tmp_path, RunSettings())
    result = await run_task(run, C_ARM)
    assert [a.passed for a in result.attempts] == [False, True]
    assert "=== FILE: gcd.c ===" in gateway.calls[0][1].messages[0].content
    assert "gcd.c" in gateway.calls[1][1].messages[2].content
