# dialect=gas-intel preset=linux-x64-gas-intel kind=df_left_set verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        std
        mov rax, rdi
        ret                     # DF is still set on return
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
