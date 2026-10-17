# dialect=gas-intel preset=linux-x64-gas-intel kind=callee_saved_clobber verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        mov rbx, rdi            # rbx is callee-saved and never restored
        lea rax, [rbx + 1]
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
