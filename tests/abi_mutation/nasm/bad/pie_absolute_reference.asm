; dialect=nasm preset=linux-x64-nasm kind=pie_absolute_reference verdict=bad
bits 64
global probe
section .data
value: dq 7
section .text
probe:
    mov eax, value         ; absolute 32-bit address: a text relocation in a PIE
    mov rax, [rax]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
