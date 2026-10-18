# dialect=gas-intel preset=linux-x64-gas-intel kind=misaligned_call verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        call helper@PLT             # rsp is 8 mod 16 here: misaligned for the callee
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
