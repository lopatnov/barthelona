# dialect=gas-intel preset=linux-x64-gas-intel kind=syscall_clobber verdict=bad
        .intel_syntax noprefix
        .text
        .globl probe
        .type probe, @function
probe:
        mov ecx, 5
        mov eax, 39             # getpid
        syscall
        mov rax, rcx            # syscall overwrote rcx with the return address
        ret
        .size probe, .-probe
        .section .note.GNU-stack,"",@progbits
