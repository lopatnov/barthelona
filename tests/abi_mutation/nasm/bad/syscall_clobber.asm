; dialect=nasm preset=linux-x64-nasm kind=syscall_clobber verdict=bad
bits 64
global probe
section .text
probe:
    mov ecx, 5
    mov eax, 39            ; getpid
    syscall
    mov rax, rcx           ; syscall overwrote rcx with the return address
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
