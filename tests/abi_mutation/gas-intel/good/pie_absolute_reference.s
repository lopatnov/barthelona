# dialect=gas-intel preset=linux-x64-gas-intel kind=pie_absolute_reference verdict=good
        .intel_syntax noprefix
        .data
value:
        .quad 7
        .text
        .globl probe
        .type probe, @function
probe:
        lea rax, [rip + value]  # RIP-relative: position independent
        mov rax, [rax]
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
