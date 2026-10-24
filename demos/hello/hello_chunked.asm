; We start with data section and entry point
section .data
    ; Define the message we want to print
    message: db 'Hello, Barthelona!',0

section .text
    global _start

_start:
    ; System call to write: 1
    mov rax, 1
    ; File descriptor 1 (stdout)
    mov rdi, 1
    ; Pointer to the message string
    mov rsi, message
    ; Number of bytes to write (without newline)
    mov rdx, 16
    syscall

    ; Exit with code 0: 60 is for sys_exit
    mov rax, 60
    mov rdi, 0
    syscall

exit_msg: db 'Hello, Barthelona!',0
