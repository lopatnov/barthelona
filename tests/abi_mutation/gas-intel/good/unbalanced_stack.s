# dialect=gas-intel preset=linux-x64-gas-intel kind=unbalanced_stack verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        push rax
        mov rax, rdi
        pop rcx
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
