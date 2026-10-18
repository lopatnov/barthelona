; dialect=nasm preset=linux-x64-nasm kind=red_zone_write verdict=good
bits 64
extern helper
global probe
section .text
probe:
    sub rsp, 24            ; a real frame: 24 + the return address keeps rsp 0 mod 16
    mov [rsp], rdi
    call helper wrt ..plt
    mov rax, [rsp]
    add rsp, 24
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
