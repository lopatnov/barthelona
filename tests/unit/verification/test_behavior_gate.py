"""The behavior gate runs real assembled programs in the emulator; they need nasm, which CI installs."""

from __future__ import annotations

import shutil

import pytest

from barthelona.verification.behavior_gate import Expectation, check_behavior

pytestmark = pytest.mark.skipif(
    shutil.which("nasm") is None, reason="nasm is not installed on this host; CI installs it"
)

_HELLO = """\
section .data
    msg db "Hello, Barthelona!", 10
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
_EXPECT = Expectation(stdout=b"Hello, Barthelona!\n")


def test_a_correct_program_passes() -> None:
    assert check_behavior(_HELLO, _EXPECT).status == "pass"


def test_a_program_that_assembles_but_prints_the_wrong_length_is_rejected() -> None:
    # The real failure seen live: the model counted 6 bytes instead of 19.
    result = check_behavior(_HELLO.replace("msg_len\n", "6\n"), _EXPECT)
    assert result.status == "fail"
    assert "stdout was 'Hello,'" in result.errors[0]


def test_a_wrong_exit_code_is_rejected() -> None:
    result = check_behavior(_HELLO.replace("xor rdi, rdi", "mov rdi, 3"), _EXPECT)
    assert result.errors == ("exit code was 3, expected 0",)


def test_writing_to_stdin_descriptor_zero_prints_nothing() -> None:
    # Another live failure: fd 0 instead of 1 is not an allowed write.
    result = check_behavior(_HELLO.replace("mov rdi, 1", "mov rdi, 0"), _EXPECT)
    assert result.status == "fail"
    assert "did not exit" in result.errors[0]


def test_a_program_without_start_cannot_be_run() -> None:
    result = check_behavior("section .text\nfoo:\n    ret\n", _EXPECT)
    assert result.errors == ("the program has no global _start label to run",)


def test_an_endless_loop_is_stopped() -> None:
    result = check_behavior("section .text\nglobal _start\n_start:\n    jmp _start\n", _EXPECT)
    assert result.status == "fail"
    assert "ran too" in result.errors[0]


def test_unexpected_syscalls_are_refused() -> None:
    result = check_behavior("section .text\nglobal _start\n_start:\n    mov rax, 57\n    syscall\n", _EXPECT)
    assert "syscall 57 is not allowed" in result.errors[0]


def test_stdin_reaches_the_program() -> None:
    echo = """\
section .bss
    buf resb 8
section .text
    global _start
_start:
    xor rax, rax
    xor rdi, rdi
    mov rsi, buf
    mov rdx, 8
    syscall
    mov rdx, rax
    mov rax, 1
    mov rdi, 1
    mov rsi, buf
    syscall
    mov rax, 60
    xor rdi, rdi
    syscall
"""
    expect = Expectation(stdout=b"abc", stdin=b"abc")
    assert check_behavior(echo, expect).status == "pass"
