; GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=dbba01c4c97a2410990413ff33290717cd25233aa351005c7357b18249ab5809
global add_one
global counter
BUF_SIZE equ 4096
struc Point
    .x: resb 8
    .y: resb 8
endstruc
