# dialect=gas-intel preset=linux-x64-gas-intel kind=misaligned_call verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        sub rsp, 8              # entry rsp is 8 mod 16; this makes it 0 mod 16 at the call
        call helper@PLT
        add rsp, 8
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
