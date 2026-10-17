# dialect=gas-intel preset=linux-x64-gas-intel expect=V6:pass
# emit_char(rdi = byte): writes that one byte to stdout. Clobbers rax, rcx, rdx, rsi, r11 (syscall).
        .intel_syntax noprefix
        .text
        .globl  emit_char
        .type   emit_char, @function
emit_char:
        push    rdi                     # the byte lives on the stack; rdi is restored by the pop
        mov     eax, 1                  # write
        mov     edi, 1                  # stdout
        mov     rsi, rsp
        mov     edx, 1
        syscall
        pop     rdi
        ret
        .size   emit_char, .-emit_char
        .section .note.GNU-stack,"",@progbits
