// GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=c12577da02a842fc790ba1862b6ae399e540234a3cf2a14dd1cf90c5686ac0a8
#include <stdio.h>
#include "../contracts.h"
int main(void) {
    unsigned long long got = (unsigned long long)add_one(41ULL);
    unsigned long long want = 42ULL;
    if (got != want) {
        printf("add_one_basic: got %llu, want %llu\n", got, want);
        return 1;
    }
    return 0;
}
