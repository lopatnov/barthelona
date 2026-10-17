.text
.globl _start
_start:
    movl $1, %eax
    foo %eax
    movl $1
