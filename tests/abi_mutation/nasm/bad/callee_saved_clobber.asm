; dialect=nasm preset=linux-x64-nasm kind=callee_saved_clobber verdict=bad
bits 64
global probe
section .text
probe:
    mov rbx, rdi           ; rbx is callee-saved and never restored
    lea rax, [rbx + 1]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
