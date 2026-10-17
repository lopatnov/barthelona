# dialect=gas-intel preset=linux-x64-gas-intel kind=missing_gnu_stack verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        mov rax, rdi
        ret
        .size probe, .-probe
