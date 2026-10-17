# dialect=gas-intel preset=linux-x64-gas-intel kind=missing_gnu_stack verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        mov rax, rdi
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
