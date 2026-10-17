"""V5: C-harness tests through the ladder (FakeExecutor) and, with Docker, the real toolchain."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.domain.contracts import ContractRegistry, RegisterContract, Symbol, SymbolKind
from barthelona.domain.enums import ABI, OS, Arch, Dialect, Level, Linker, ObjFormat, RunEnv
from barthelona.domain.project import TargetProfile
from barthelona.domain.verification import Expectation, TestCase, TestKind, TestOrigin
from barthelona.executors import AgentExecutor, LocalTransport
from barthelona.executors._types import ExecResult
from barthelona.executors.fake import FakeExecutor
from barthelona.toolchains.nasm import NasmAdapter
from barthelona.verification import LadderOptions, dod_satisfied, run_ladder
from barthelona.verification.harness import harness_objects

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "harness"


def _registry() -> ContractRegistry:
    target = TargetProfile(
        preset="linux-x64-test",
        dialect=Dialect.NASM,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )
    symbols = {
        "add_one": Symbol(
            name="add_one",
            kind=SymbolKind.FUNC,
            module="src/math.asm",
            inputs=[RegisterContract(reg="rdi", type="u64")],
            outputs=[RegisterContract(reg="rax", type="u64")],
        ),
        "_start": Symbol(name="_start", kind=SymbolKind.FUNC, module="src/main.asm", calls=["add_one"]),
    }
    return ContractRegistry(version=1, target=target, symbols=symbols)


def _case(ret: int = 42) -> TestCase:
    return TestCase(
        id="add_one_basic",
        kind=TestKind.C_HARNESS,
        symbol="add_one",
        level=Level.V5,
        inputs={"rdi": 41},
        expect=Expectation(ret=ret),
        origin=TestOrigin.USER,
    )


def _sources(tmp_path: Path) -> list[Path]:
    path = tmp_path / "math.asm"
    path.write_text("; stub\n", encoding="utf-8")
    return [path]


def _sandbox(returncode: int = 0, stdout: bytes = b"") -> FakeExecutor:
    binary = "/fake/work/t/0/harness_add_one_basic"
    result = ExecResult(returncode=returncode, stdout=stdout, stderr=b"", elapsed=0.0)
    return FakeExecutor(executor_id="sandbox", may_run_untrusted=True, responses={(binary,): result})


def _toolchain() -> FakeExecutor:
    """A toolchain whose nm reports exactly what the registry expects of math.asm."""
    nm = ExecResult(returncode=0, stdout=b"add_one T 0 \n", stderr=b"", elapsed=0.0)
    return FakeExecutor(responses={("nm", "-P", "-g", "/fake/work/t/0/math.o"): nm})


def test_the_entry_module_is_left_out_of_the_harness_link() -> None:
    objects = ["/w/math.o", "/w/main.o"]
    assert harness_objects(_registry(), objects, "_start") == ["/w/math.o"]
    assert harness_objects(_registry(), objects, "unknown") == objects


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        (LadderOptions(sandbox=_sandbox(), tests=[_case()]), "contract registry"),
        (LadderOptions(contracts=_registry(), tests=[_case()]), "sandbox"),
        (LadderOptions(contracts=_registry(), sandbox=_sandbox()), "c_harness"),
    ],
)
async def test_v5_is_unsupported_without_its_inputs(
    tmp_path: Path, options: LadderOptions, reason: str
) -> None:
    results = await run_ladder(Level.V5, FakeExecutor(), NasmAdapter(), _sources(tmp_path), "t", 0, options)
    assert results[-1].status == "unsupported"
    assert reason in results[-1].diagnostics[0].message


async def test_passing_harness_makes_v5_pass(tmp_path: Path) -> None:
    options = LadderOptions(contracts=_registry(), sandbox=_sandbox(), tests=[_case()])
    results = await run_ladder(Level.V5, _toolchain(), NasmAdapter(), _sources(tmp_path), "t", 0, options)
    assert results[-1].status == "pass"


async def test_failing_harness_reports_its_output(tmp_path: Path) -> None:
    sandbox = _sandbox(returncode=1, stdout=b"add_one_basic: got 42, want 43\n")
    options = LadderOptions(contracts=_registry(), sandbox=sandbox, tests=[_case(43)])
    results = await run_ladder(Level.V5, _toolchain(), NasmAdapter(), _sources(tmp_path), "t", 0, options)
    assert results[-1].status == "fail"
    assert results[-1].diagnostics[0].code == "harness.failed"
    assert "got 42, want 43" in results[-1].diagnostics[0].message
    assert not dod_satisfied([Level.V5], results)


@pytest.mark.docker
async def test_harness_runs_against_the_real_toolchain() -> None:
    sources = [_FIXTURES / "math.asm", _FIXTURES / "main.asm"]
    wrong = _case(43).model_copy(update={"id": "wrong_expectation"})
    executor = AgentExecutor(LocalTransport())
    try:
        options = LadderOptions(contracts=_registry(), sandbox=executor.sandbox(), tests=[_case(), wrong])
        results = await run_ladder(Level.V5, executor, NasmAdapter(), sources, "v5-real", 0, options)
    finally:
        await executor.aclose()
    assert [r.status for r in results[:3]] == ["pass", "pass", "pass"]
    v5 = results[-1]
    assert v5.status == "fail"
    assert [d.code for d in v5.diagnostics] == ["harness.failed"]
    assert v5.diagnostics[0].message.startswith("wrong_expectation: wrong_expectation: got 42, want 43")
