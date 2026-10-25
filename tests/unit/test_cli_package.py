"""`runs package` and `check`: a green run becomes repository files; the generated CI re-checks them."""

from __future__ import annotations

import json
import shutil
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.cli import app
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
    RunEnv,
    RunStatus,
    StopReason,
    TargetProfile,
    TestCase,
    TestKind,
    TestOrigin,
)
from barthelona.domain.layout import SOURCE_FILE, SPEC_FILE, TESTS_FILE
from barthelona.persistence import open_store

REF = "d76afc5ed3f5611bff1f7594035a1fbc4ac65686"
SOURCE = "section .text\nglobal _start\n_start:\n    mov rax, 60\n    syscall"
HELLO = """section .data
msg db "hello", 10
len equ $ - msg
section .text
global _start
_start:
    mov rax, 1
    mov rdi, 1
    mov rsi, msg
    mov rdx, len
    syscall
    mov rax, 60
    xor rdi, rdi
    syscall"""


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


def _green_run(tmp_path: Path, stop: StopReason = StopReason.GREEN, *submit_args: str) -> str:
    db, runs = str(tmp_path / "app.sqlite"), str(tmp_path / "runs")
    submitted = CliRunner().invoke(
        app, ["runs", "submit", "Print hello.", "--db", db, "--runs", runs, *submit_args]
    )
    run_id = submitted.output.strip()
    with closing(open_store(tmp_path / "app.sqlite")) as store:
        store.set_run_status(run_id, RunStatus.RUNNING)
        store.record_llm_call(run_id, _call("auto", 100, 20, 4000))
        store.set_run_status(run_id, RunStatus.STOPPED, stop)
    folder = tmp_path / "runs" / run_id
    (folder / SPEC_FILE).write_text(_spec().model_dump_json(), encoding="utf-8")
    cases = [case.model_dump(mode="json") for case in _cases()]
    (folder / TESTS_FILE).write_text(json.dumps(cases), encoding="utf-8")
    (folder / SOURCE_FILE).write_text(SOURCE + "\n", encoding="utf-8")
    return run_id


def _package(tmp_path: Path, run_id: str, *extra: str):  # type: ignore[no-untyped-def]  # typer's Result
    args = ["runs", "package", run_id, "--out", str(tmp_path / "out"), "--barthelona-ref", REF]
    return CliRunner().invoke(
        app, [*args, "--db", str(tmp_path / "app.sqlite"), "--runs", str(tmp_path / "runs"), *extra]
    )


def test_package_writes_the_project_files_of_a_green_run(tmp_path: Path) -> None:
    result = _package(tmp_path, _green_run(tmp_path))
    assert result.exit_code == 0, result.output
    out = tmp_path / "out"
    assert (out / "src" / "hello.asm").read_text(encoding="utf-8") == SOURCE + "\n"
    assert "meterless/auto" in (out / "README.md").read_text(encoding="utf-8")
    assert (out / ".github" / "workflows" / "release.yml").exists()


def test_package_without_out_writes_into_the_runs_demos_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = _green_run(tmp_path, StopReason.GREEN, "--project", "hello-en")
    args = ["runs", "package", run_id, "--barthelona-ref", REF, "--db", "app.sqlite", "--runs", "runs"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demos" / "hello-en" / "README.md").exists()


def test_package_without_out_needs_a_demos_folder_on_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = _green_run(tmp_path)
    args = ["runs", "package", run_id, "--barthelona-ref", REF, "--db", "app.sqlite", "--runs", "runs"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert not (tmp_path / "workspaces").exists()


def test_package_refuses_a_run_that_did_not_stop_green(tmp_path: Path) -> None:
    result = _package(tmp_path, _green_run(tmp_path, StopReason.MAX_ATTEMPTS))
    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_package_does_not_overwrite_without_force(tmp_path: Path) -> None:
    run_id = _green_run(tmp_path)
    assert _package(tmp_path, run_id).exit_code == 0
    readme = tmp_path / "out" / "README.md"
    readme.write_text("edited by hand", encoding="utf-8")
    assert _package(tmp_path, run_id).exit_code == 2
    assert readme.read_text(encoding="utf-8") == "edited by hand"
    assert _package(tmp_path, run_id, "--force").exit_code == 0
    assert readme.read_text(encoding="utf-8") != "edited by hand"


@pytest.mark.skipif(shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it")
def test_check_passes_a_program_that_matches_the_golden_tests(tmp_path: Path) -> None:
    source = tmp_path / "hello.asm"
    source.write_text(HELLO + "\n", encoding="utf-8")
    tests = tmp_path / "golden.json"
    tests.write_text(json.dumps([case.model_dump(mode="json") for case in _cases()]), encoding="utf-8")
    result = CliRunner().invoke(app, ["check", str(source), "--tests", str(tests)])
    assert result.exit_code == 0, result.output
    assert "pass (1 tests)" in result.output


@pytest.mark.skipif(shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it")
def test_check_exits_1_and_names_the_failing_test(tmp_path: Path) -> None:
    source = tmp_path / "hello.asm"
    source.write_text(HELLO.replace("hello", "howdy") + "\n", encoding="utf-8")
    tests = tmp_path / "golden.json"
    tests.write_text(json.dumps([case.model_dump(mode="json") for case in _cases()]), encoding="utf-8")
    result = CliRunner().invoke(app, ["check", str(source), "--tests", str(tests)])
    assert result.exit_code == 1
    assert "test T1" in result.output
