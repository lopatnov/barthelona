; dialect=nasm preset=linux-x64-nasm kind=misaligned_call verdict=bad
bits 64
extern helper
global probe
section .text
probe:
    call helper wrt ..plt            ; rsp is 8 mod 16 here: misaligned for the callee
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
