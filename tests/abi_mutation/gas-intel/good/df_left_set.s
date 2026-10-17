# dialect=gas-intel preset=linux-x64-gas-intel kind=df_left_set verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        std
        mov rax, rdi
        cld                     # DF is clear again on return
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
