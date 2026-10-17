; dialect=nasm preset=linux-x64-nasm kind=misaligned_call verdict=good
bits 64
extern helper
global probe
section .text
probe:
    sub rsp, 8             ; entry rsp is 8 mod 16; this makes it 0 mod 16 at the call
    call helper wrt ..plt
    add rsp, 8
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
