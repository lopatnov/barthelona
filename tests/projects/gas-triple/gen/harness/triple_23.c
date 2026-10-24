// GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=5ef6e71ab05097f50c1d338ee0cdeeac912597a24ac223eb97cc6586fe410cba
#include <stdio.h>
#include "../contracts.h"
int main(void) {
    unsigned long long got = (unsigned long long)triple(23ULL);
    unsigned long long want = 69ULL;
    if (got != want) {
        printf("triple_23: got %llu, want %llu\n", got, want);
        return 1;
    }
    return 0;
}
