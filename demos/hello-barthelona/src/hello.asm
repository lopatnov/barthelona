; =====================================================================
; Hello Barthelona — a minimal Linux x86-64 program using only syscalls.
; This program writes "Hello Barthelona\n" to standard output (stdout)
; and then exits with a status code of 0.
; Build:  nasm -f elf64 hello.asm -o hello.o && ld hello.o -o hello
; =====================================================================

section .data
    msg         db 'Hello Barthelona', 10  ; Define the message string with a newline
    msg_len     equ $ - msg                 ; Calculate the length of the message

section .text
    global _start                            ; Define the entry point for the program

_start:
    ; ---- sys_write (fd=1, buf=msg, count=msg_len) ----
    mov     rax, 1                          ; syscall number for sys_write
    mov     rdi, 1                          ; file descriptor 1 (stdout)
    lea     rsi, [rel msg]                  ; load the address of the message
    mov     rdx, msg_len                    ; set the number of bytes to write
    syscall                                 ; invoke the syscall to write the message

    ; ---- sys_exit (status=0) ----
    mov     rax, 60                         ; syscall number for sys_exit
    xor     rdi, rdi                        ; set exit status to 0
    syscall                                 ; invoke the syscall to exit the program
