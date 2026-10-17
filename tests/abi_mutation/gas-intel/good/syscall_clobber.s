# dialect=gas-intel preset=linux-x64-gas-intel kind=syscall_clobber verdict=good
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        mov eax, 39             # getpid
        syscall
        ret                     # only rax is read after the syscall
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
