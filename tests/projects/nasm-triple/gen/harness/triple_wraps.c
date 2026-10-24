// GENERATED from contracts.yaml, do not edit. barthelona-gen v1 body-sha256=78d6687724ab32f922a48da252820f94f93518ac1f04ab58848ae57d9f30cd66
#include <stdio.h>
#include "../contracts.h"
int main(void) {
    unsigned long long got = (unsigned long long)triple(6148914691236517205ULL);
    unsigned long long want = 18446744073709551615ULL;
    if (got != want) {
        printf("triple_wraps: got %llu, want %llu\n", got, want);
        return 1;
    }
    return 0;
}
