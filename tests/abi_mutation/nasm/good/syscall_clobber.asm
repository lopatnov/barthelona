; dialect=nasm preset=linux-x64-nasm kind=syscall_clobber verdict=good
bits 64
global probe
section .text
probe:
    mov eax, 39            ; getpid
    syscall
    ret                    ; only rax is read after the syscall

section .note.GNU-stack noalloc noexec nowrite progbits
