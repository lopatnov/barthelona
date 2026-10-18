; dialect=nasm preset=linux-x64-nasm kind=df_left_set verdict=bad
bits 64
global probe
section .text
probe:
    std
    mov rax, rdi
    ret                    ; DF is still set on return

section .note.GNU-stack noalloc noexec nowrite progbits
