; Smoke test for bart-tc / bart-run: writes "ok\n" and exits 0 (linux-x64, syscalls only).
global _start

section .rodata
msg: db "ok", 10

section .text
_start:
    mov eax, 1          ; write
    mov edi, 1          ; stdout
    lea rsi, [rel msg]
    mov edx, 3
    syscall
    mov eax, 60         ; exit
    xor edi, edi
    syscall
