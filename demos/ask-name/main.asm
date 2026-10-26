; Program: Prompts for a name and prints a personalized greeting.
; This program uses Linux x86-64 syscalls (write, read, exit) only and does not use libc.

section .data
    prompt      db 'Enter your name: '   ; Prompt message for user input
    prompt_len  equ $ - prompt             ; Length of the prompt message
    greeting    db 'Hello '                ; Greeting prefix (6 bytes)
    newline     db 10                      ; Newline character (ASCII LF)

section .bss
    buf         resb 256                   ; Buffer for input (256 bytes)

section .text
    global _start                          ; Entry point for the program

_start:
    ; Write prompt to stdout (fd=1) using sys_write (rax=1)
    mov rax, 1                              ; syscall number for sys_write
    mov rdi, 1                              ; file descriptor 1 (stdout)
    lea rsi, [rel prompt]                   ; load address of prompt message (RIP-relative)
    mov rdx, prompt_len                     ; length of the prompt message
    syscall                                 ; invoke kernel write

    ; Read line from stdin (fd=0) into buf using sys_read (rax=0)
    mov rax, 0                              ; syscall number for sys_read
    mov rdi, 0                              ; file descriptor 0 (stdin)
    lea rsi, [rel buf]                      ; load address of buffer (RIP-relative)
    mov rdx, 256                            ; maximum bytes to read
    syscall                                 ; invoke kernel read
    ; rax now contains the number of bytes read (including trailing newline)

    ; Process input to find length excluding the newline
    mov r8, rax                             ; save number of bytes read in r8
    xor rcx, rcx                            ; clear rcx for indexing

.find_nl:
    cmp rcx, r8                             ; compare index with bytes read
    jae .done_scan                          ; if index >= length, exit loop (no newline found)
    cmp byte [rel buf + rcx], 10           ; check for newline character (ASCII 10)
    je .found_nl                            ; if found, jump to found_nl
    inc rcx                                 ; increment index
    jmp .find_nl                            ; repeat the search

.found_nl:
    mov r8, rcx                             ; set length to index of newline (exclude it)

.done_scan:
    ; Write "Hello " prefix using sys_write (rax=1)
    mov rax, 1                              ; syscall number for sys_write
    mov rdi, 1                              ; file descriptor 1 (stdout)
    lea rsi, [rel greeting]                 ; load address of greeting message (RIP-relative)
    mov rdx, 6                              ; length of "Hello "
    syscall                                 ; invoke kernel write

    ; Write name (buffer up to newline) using sys_write (rax=1)
    mov rax, 1                              ; syscall number for sys_write
    mov rdi, 1                              ; file descriptor 1 (stdout)
    lea rsi, [rel buf]                      ; load address of buffer (RIP-relative)
    mov rdx, r8                             ; length of name without newline
    syscall                                 ; invoke kernel write

    ; Write final newline using sys_write (rax=1)
    mov rax, 1                              ; syscall number for sys_write
    mov rdi, 1                              ; file descriptor 1 (stdout)
    lea rsi, [rel newline]                  ; load address of newline character (RIP-relative)
    mov rdx, 1                              ; length of newline (1 byte)
    syscall                                 ; invoke kernel write

    ; Exit with status 0 using sys_exit (rax=60)
    mov rax, 60                             ; syscall number for sys_exit
    xor rdi, rdi                            ; status 0
    syscall                                 ; invoke kernel exit
