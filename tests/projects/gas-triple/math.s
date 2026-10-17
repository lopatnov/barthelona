# dialect=gas-intel preset=linux-x64-gas-intel expect=V6:pass
# triple(rdi) -> rax = 3 * rdi, wrapping at 64 bits.
        .intel_syntax noprefix
        .text
        .globl  triple
        .type   triple, @function
triple:
        lea     rax, [rdi + rdi*2]
        ret
        .size   triple, .-triple
        .section .note.GNU-stack,"",@progbits
