; add_one(rdi) -> rax: the function under test in the V5 integration test.
bits 64
global add_one

section .text
add_one:
    lea rax, [rdi + 1]
    ret

section .note.GNU-stack noalloc noexec nowrite progbits
