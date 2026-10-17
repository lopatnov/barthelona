; dialect=nasm preset=linux-x64-nasm kind=red_zone_write verdict=bad
bits 64
extern helper
global probe
section .text
probe:
    sub rsp, 8
    mov [rsp - 8], rdi     ; red zone in a non-leaf function: the call below overwrites it
    call helper wrt ..plt
    mov rax, [rsp - 8]
    add rsp, 8
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
