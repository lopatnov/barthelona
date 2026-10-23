"""The host assemble oracle: pass, fail with NASM's errors, refusals and an unavailable assembler."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from barthelona.verification.asm_gate import assemble_source, find_nasm

_HELLO = """\
section .data
msg db "Hello", 10
msg_len equ $ - msg
section .text
global _start
_start:
    mov rax, 1
    mov rdi, 1
    mov rsi, msg
    mov rdx, msg_len
    syscall
    mov rax, 60
    xor rdi, rdi
    syscall
"""


def _runner(returncode: int, stderr: bytes = b"") -> Any:
    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert isinstance(argv, list) and "shell" not in kwargs  # argv list only (invariant 9)
        return subprocess.CompletedProcess(argv, returncode, b"", stderr)

    return run


def test_a_clean_assemble_passes() -> None:
    assert assemble_source(_HELLO, "nasm", _runner(0)).status == "pass"


def test_nasm_errors_come_back_with_their_line_numbers() -> None:
    stderr = b"main.asm:19: error: label `msg' inconsistently redefined\nmain.asm:25: warning: noise\n"
    result = assemble_source(_HELLO, "nasm", _runner(1, stderr))
    assert result.status == "fail"
    assert result.errors == ("line 19: label `msg' inconsistently redefined",)


def test_an_unparsable_failure_still_reports_something() -> None:
    result = assemble_source(_HELLO, "nasm", _runner(1, b"boom"))
    assert (result.status, result.errors) == ("fail", ("boom",))


@pytest.mark.parametrize(
    "source", ['%include "/etc/passwd"', 'data: incbin "secret.bin"', "%pathsearch x 'y'"]
)
def test_directives_that_read_host_files_are_refused_without_running_nasm(source: str) -> None:
    def never(argv: list[str], **kwargs: Any) -> None:
        raise AssertionError("nasm must not run")

    result = assemble_source(source, "nasm", never)
    assert result.status == "fail"
    assert "refused" in result.errors[0]


def test_an_empty_source_fails() -> None:
    assert assemble_source("  \n", "nasm", _runner(0)).status == "fail"


def test_a_missing_binary_is_unavailable_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = assemble_source(_HELLO, env={})
    assert result.status == "unavailable"
    assert "NASM_PATH" in result.errors[0]


def _fake_nasm(folder: Path) -> Path:
    folder.mkdir(parents=True)
    binary = folder / "nasm.exe"
    binary.write_bytes(b"")
    return binary


def test_nasm_path_may_name_the_folder_that_holds_nasm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    binary = _fake_nasm(tmp_path / "NASM")
    assert find_nasm(env={"NASM_PATH": str(tmp_path / "NASM")}) == str(binary)


def test_an_explicit_path_wins_over_the_environment_and_must_exist(tmp_path: Path) -> None:
    binary = _fake_nasm(tmp_path / "A")
    other = _fake_nasm(tmp_path / "B")
    assert find_nasm(str(binary), {"NASM_PATH": str(other.parent)}) == str(binary)
    assert find_nasm(str(tmp_path / "missing" / "nasm.exe"), {"NASM_PATH": str(other.parent)}) is None


def test_the_usual_windows_install_folder_is_found_without_any_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    binary = _fake_nasm(tmp_path / "bin" / "NASM")
    assert find_nasm(env={"LOCALAPPDATA": str(tmp_path)}) == str(binary)


def test_a_wrong_environment_hint_falls_through_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/nasm" if name == "nasm" else None)
    assert find_nasm(env={"NASM_PATH": str(tmp_path / "nowhere")}) == "/usr/bin/nasm"


def test_a_timeout_is_unavailable() -> None:
    def hang(argv: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(argv, 1)

    assert assemble_source(_HELLO, "nasm", hang).status == "unavailable"


@pytest.mark.skipif(shutil.which("nasm") is None, reason="nasm is not installed on this host")
def test_real_nasm_accepts_hello_and_rejects_a_program_written_twice() -> None:
    assert assemble_source(_HELLO).status == "pass"
    twice = assemble_source(_HELLO + _HELLO)
    assert twice.status == "fail"
    assert any("redefined" in error for error in twice.errors)
