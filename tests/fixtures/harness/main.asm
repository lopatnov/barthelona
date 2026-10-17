; Entry module: V5 leaves it out because the generated harness has its own main.
global _start
extern add_one

section .text
_start:
    mov rdi, 41
    call add_one
    xor edi, edi
    mov eax, 60
    syscall

section .note.GNU-stack noalloc noexec nowrite progbits
