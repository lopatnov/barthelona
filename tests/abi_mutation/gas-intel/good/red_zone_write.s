# dialect=gas-intel preset=linux-x64-gas-intel kind=red_zone_write verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        sub rsp, 24             # a real frame: 24 + the return address keeps rsp 0 mod 16
        mov [rsp], rdi
        call helper@PLT
        mov rax, [rsp]
        add rsp, 24
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
