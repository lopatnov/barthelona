"""`render_project`: the files of a green single-module run, all from templates and the run's own data."""

from __future__ import annotations

import json

import pytest

from barthelona.domain import (
    ABI,
    OS,
    Arch,
    Dialect,
    Expectation,
    Level,
    Linker,
    LLMCallRecord,
    ModuleSpec,
    ObjFormat,
    ProjectSpec,
    Requirement,
    Run,
    RunBudget,
    RunEnv,
    RunMode,
    TargetProfile,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.domain.run import Profile
from barthelona.scaffold import UnsupportedCiTarget, render_project

REF = "d76afc5ed3f5611bff1f7594035a1fbc4ac65686"
SOURCE = "section .text\nglobal _start\n_start:\n    mov rax, 60\n    syscall"


def _target(dialect: Dialect = Dialect.NASM) -> TargetProfile:
    return TargetProfile(
        preset="linux-x64-nasm-static",
        dialect=dialect,
        arch=Arch.X86_64,
        os=OS.LINUX,
        abi=ABI.SYSV64,
        obj_format=ObjFormat.ELF64,
        link=Linker.LD,
        run_env=RunEnv.DOCKER_NATIVE,
    )


def _spec(modules: list[str] | None = None, dialect: Dialect = Dialect.NASM) -> ProjectSpec:
    return ProjectSpec(
        id="s1",
        slug="hello",
        request_original="Print hello.",
        request_lang="en",
        summary_en="Prints hello and exits with 0.",
        target=_target(dialect),
        modules=[ModuleSpec(path=p, purpose="entry") for p in modules or ["src/hello.asm"]],
        requirements=[Requirement(id="R1", text="Writes hello and a newline.", test_ids=["T1"])],
    )


def _run() -> Run:
    return Run(
        id="run-1",
        mode=RunMode.CREATE,
        workspace="workspaces/run-1",
        target=_target(),
        profile=Profile.METERLESS,
        policy_version="v1",
        budget=RunBudget(wall_s=3600, tokens=400_000, cloud_allowed=True),
    )


def _cases() -> list[TestCase]:
    return [
        TestCase(
            id="T1",
            kind=TestKind.IO_GOLDEN,
            level=Level.V6,
            inputs={"stdin": ""},
            expect=Expectation(stdout="hello\n", exit_code=0),
            origin=TestOrigin.TEST_AUTHOR,
        )
    ]


def _call(model: str, tokens_in: int, tokens_out: int, latency_ms: int) -> LLMCallRecord:
    return LLMCallRecord(
        provider="meterless",
        model=model,
        prompt_hash="a" * 64,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        stop_reason="stop",
    )


def _render(**changes: object) -> dict[str, str]:
    args: dict[str, object] = {
        "run": _run(),
        "spec": _spec(),
        "cases": _cases(),
        "source": SOURCE,
        "request": "Print hello.\n",
        "calls": [_call("auto", 100, 20, 4000), _call("auto", 50, 10, 1000), _call("deep", 900, 300, 9000)],
        "barthelona_ref": REF,
    }
    return render_project(**(args | changes))  # type: ignore[arg-type]


def test_the_project_has_the_source_the_tests_the_request_the_readme_and_the_workflows() -> None:
    assert sorted(_render()) == [
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "README.md",
        "prompt/request.txt",
        "src/hello.asm",
        "tests/golden.json",
    ]


def test_the_source_and_the_golden_tests_are_the_run_data_unchanged() -> None:
    files = _render()
    assert files["src/hello.asm"] == SOURCE + "\n"
    cases = json.loads(files["tests/golden.json"])
    assert cases[0]["id"] == "T1"
    assert cases[0]["expect"]["stdout"] == "hello\n"
    assert files["prompt/request.txt"] == "Print hello.\n"


def test_the_readme_says_what_it_does_how_to_check_it_and_how_it_was_made() -> None:
    readme = _render()["README.md"]
    assert "Prints hello and exits with 0." in readme
    assert "**R1**: Writes hello and a newline." in readme
    assert "nasm -f elf64 -o build/hello.o src/hello.asm" in readme
    assert "python -m barthelona check src/hello.asm --tests tests/golden.json" in readme
    assert "> Print hello." in readme
    assert "Run `run-1`, profile `meterless`" in readme


def test_the_readme_totals_calls_tokens_and_seconds_per_model() -> None:
    readme = _render()["README.md"]
    assert "| `meterless/auto` | 2 | 150 | 30 | 5.0 |" in readme
    assert "| `meterless/deep` | 1 | 900 | 300 | 9.0 |" in readme


def test_the_ci_checks_the_golden_tests_with_the_pinned_barthelona() -> None:
    ci = _render()[".github/workflows/ci.yml"]
    assert f"BARTHELONA_REF: {REF}" in ci
    assert "python -m barthelona check src/hello.asm --tests tests/golden.json" in ci
    assert "contracts" not in ci


def test_the_same_run_data_gives_the_same_bytes() -> None:
    first, second = _render(), _render()
    assert first == second


def test_a_project_with_several_modules_is_refused() -> None:
    spec = _spec(["src/main.asm", "src/util.asm"])
    with pytest.raises(UnsupportedCiTarget, match="single-module"):
        _render(spec=spec)


def test_a_gas_project_is_refused_by_the_golden_ci() -> None:
    spec = _spec(dialect=Dialect.GAS_INTEL)
    with pytest.raises(UnsupportedCiTarget, match="NASM"):
        _render(spec=spec)


def test_a_branch_name_is_not_a_commit() -> None:
    with pytest.raises(UnsupportedCiTarget, match="full commit sha"):
        _render(barthelona_ref="main")
