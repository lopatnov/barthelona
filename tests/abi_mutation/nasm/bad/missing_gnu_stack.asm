; dialect=nasm preset=linux-x64-nasm kind=missing_gnu_stack verdict=bad
bits 64
global probe
section .text
probe:
    mov rax, rdi
    ret
