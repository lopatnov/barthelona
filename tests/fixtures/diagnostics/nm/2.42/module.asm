section .text
global add_one
extern helper
add_one:
    call helper
    inc rax
    ret
local_fn:
    ret
section .data
global counter
counter: dq 0
