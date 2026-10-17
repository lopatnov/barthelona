# dialect=gas-intel preset=linux-x64-gas-intel kind=callee_saved_clobber verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        push rbx                # saved before use
        mov rbx, rdi
        lea rax, [rbx + 1]
        pop rbx
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
