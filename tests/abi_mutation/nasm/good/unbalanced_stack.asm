; dialect=nasm preset=linux-x64-nasm kind=unbalanced_stack verdict=good
bits 64
global probe
section .text
probe:
    push rax
    mov rax, rdi
    pop rcx
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
