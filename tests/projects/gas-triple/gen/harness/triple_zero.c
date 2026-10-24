// GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=3254c80900dee0b2347162d4cc249300e4bc2a2605e6e649f23be53ba8e3942d
#include <stdio.h>
#include "../contracts.h"
int main(void) {
    unsigned long long got = (unsigned long long)triple(0ULL);
    unsigned long long want = 0ULL;
    if (got != want) {
        printf("triple_zero: got %llu, want %llu\n", got, want);
        return 1;
    }
    return 0;
}
