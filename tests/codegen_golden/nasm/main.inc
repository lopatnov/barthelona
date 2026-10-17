; GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=509e52d7c9751eb0de63c22f21a86e5932377456a50c9494d4ac9668e989b5c1
global main_loop
extern add_one
extern sys_exit
BUF_SIZE equ 4096
struc Point
    .x: resb 8
    .y: resb 8
endstruc
