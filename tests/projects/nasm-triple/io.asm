; dialect=nasm preset=linux-x64-nasm expect=V6:pass
; emit_char(rdi = byte): writes that one byte to stdout. Clobbers rax, rcx, rdx, rsi, r11 (syscall).
bits 64
global emit_char

section .text
emit_char:
    push rdi                ; the byte lives on the stack; rdi is restored by the pop
    mov eax, 1              ; write
    mov edi, 1              ; stdout
    mov rsi, rsp
    mov edx, 1
    syscall
    pop rdi
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
