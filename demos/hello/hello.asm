```asm
section .data
    msg db 'Hello, Barthelona!', 0xa   ; Message including newline character
    
section .text
    global _start
_start:
    ; System call to write (sys_write): 1
    mov rax, 0x01                   ; Syscall number for write
    mov rdi, 0x00                    ; File descriptor 1 (stdout)
    mov rsi, msg                     ; Pointer to message
    mov rdx, 6                       ; Length of message (17 bytes including newline)
    syscall
    
    ; System call to exit (sys_exit): 60
    mov rax, 0x3c                    ; Syscall number for exit
    mov rdi, 0x00                    ; Exit code 0
    syscall
```
