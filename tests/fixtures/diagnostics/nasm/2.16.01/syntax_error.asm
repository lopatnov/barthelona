section .text
global _start
_start:
    mov eax, 1
    foo bar, baz
    mov rax, [
