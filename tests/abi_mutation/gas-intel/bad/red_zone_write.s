# dialect=gas-intel preset=linux-x64-gas-intel kind=red_zone_write verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        sub rsp, 8
        mov [rsp - 8], rdi      # red zone in a non-leaf function: the call below overwrites it
        call helper@PLT
        mov rax, [rsp - 8]
        add rsp, 8
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
