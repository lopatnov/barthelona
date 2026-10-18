; dialect=nasm preset=linux-x64-nasm kind=unbalanced_stack verdict=bad
bits 64
global probe
section .text
probe:
    push rax
    mov rax, rdi
    ret                    ; the push is never popped: ret takes the pushed value as the return address

section .note.GNU-stack noalloc noexec nowrite progbits
