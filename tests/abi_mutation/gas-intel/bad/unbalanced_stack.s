# dialect=gas-intel preset=linux-x64-gas-intel kind=unbalanced_stack verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        push rax
        mov rax, rdi
        ret                     # the push is never popped: ret takes the pushed value as the return address
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
