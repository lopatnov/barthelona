; dialect=nasm preset=linux-x64-nasm expect=V6:pass
; Entry module: prints "E\n" (triple(23) = 69 = 'E') and exits 0.
bits 64
global _start
extern triple
extern emit_char

section .text
_start:
    mov edi, 23
    call triple
    mov rdi, rax
    call emit_char
    mov edi, 10
    call emit_char
    xor edi, edi
    mov eax, 60             ; exit
    syscall

section .note.GNU-stack noalloc noexec nowrite progbits
