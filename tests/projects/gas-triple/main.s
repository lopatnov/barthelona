# dialect=gas-intel preset=linux-x64-gas-intel expect=V6:pass
# Entry module: prints "E\n" (triple(23) = 69 = 'E') and exits 0.
        .intel_syntax noprefix
        .text
        .globl  _start
        .type   _start, @function
_start:
        mov     edi, 23
        call    triple
        mov     rdi, rax
        call    emit_char
        mov     edi, 10
        call    emit_char
        xor     edi, edi
        mov     eax, 60                 # exit
        syscall
        .size   _start, .-_start
        .section .note.GNU-stack,"",@progbits
