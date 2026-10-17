; dialect=nasm preset=linux-x64-nasm expect=V6:pass
; triple(rdi) -> rax = 3 * rdi, wrapping at 64 bits.
bits 64
global triple

section .text
triple:
    lea rax, [rdi + rdi*2]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
