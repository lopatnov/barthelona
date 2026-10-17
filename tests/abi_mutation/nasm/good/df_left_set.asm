; dialect=nasm preset=linux-x64-nasm kind=df_left_set verdict=good
bits 64
global probe
section .text
probe:
    std
    mov rax, rdi
    cld                    ; DF is clear again on return
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
