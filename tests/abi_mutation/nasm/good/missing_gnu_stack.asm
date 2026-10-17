; dialect=nasm preset=linux-x64-nasm kind=missing_gnu_stack verdict=good
bits 64
global probe
section .text
probe:
    mov rax, rdi
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
