section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg

section .text
    global _start

_start:
    mov rax, 1          ; sys_write
    mov rdi, 1          ; stdout
    mov rsi, msg        ; message address
```asm
section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg

section .text
    global _start

_start:
    mov rax, 1          ; sys_write
    mov rdi, 1          ; stdout
    mov rsi, msg        ; message address
    mov rdx, msg_len    ; message length
    syscall

    mov rax, 60         ; sys_exit
    xor rdi, rdi        ; exit
```asm
section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg

section .text
    global _start

_start:
    mov rax, 1          ; sys_write
    mov rdi, 1          ; stdout
    mov rsi, msg        ; message address
    mov rdx, msg_len    ; message length
    syscall

    mov rax, 60         ; sys_exit
    xor rdi, rdi        ; exit code 0
    syscall
