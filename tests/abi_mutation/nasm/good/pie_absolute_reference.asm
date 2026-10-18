; dialect=nasm preset=linux-x64-nasm kind=pie_absolute_reference verdict=good
bits 64
default rel
global probe
section .data
value: dq 7
section .text
probe:
    lea rax, [rel value]   ; RIP-relative: position independent
    mov rax, [rax]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
