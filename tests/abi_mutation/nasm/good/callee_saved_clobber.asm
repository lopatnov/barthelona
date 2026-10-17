; dialect=nasm preset=linux-x64-nasm kind=callee_saved_clobber verdict=good
bits 64
global probe
section .text
probe:
    push rbx               ; saved before use
    mov rbx, rdi
    lea rax, [rbx + 1]
    pop rbx
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
