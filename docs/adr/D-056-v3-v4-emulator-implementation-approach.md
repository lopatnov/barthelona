# D-056: V3/V4 are a library over relocatable objects, and a behavior gate decides what a program does

- Status: Proposed
- Date: 2026-10-24
- Amends: D-007, D-046

## Context

The ladder (§13.1) names V3 (static ABI lint) and V4 (Unicorn dynamic ABI checks) as Phase 2 work, and the mutation corpus (`tests/abi_mutation/`, `kinds.yaml`) already says which of them must flag each kind. A first draft in PR #231 could not run: the checks returned "not implemented", the Unicorn register constants were undefined, the syscall hook dropped the output and the corpus tests asserted only that the snippet files exist.

The hackathon work needs more than "NASM accepts it": a program that assembles can still print the wrong text (seen live: a length of 6 for a 19-byte string, file descriptor 0 instead of 1). The host may have no linker (the owner's Windows PC has NASM only), and generated code must never run on the host (invariant 2).

## Decision

1. **A package `src/barthelona/emulator/`** is the only place that imports `unicorn`, `capstone` and `pyelftools` (SDK containment, D-045):
   - `object_image` loads a relocatable x86-64 ELF (`nasm -f elf64`, `as`) without linking: sections are laid out, `R_X86_64_64/PC32/PLT32/32/32S` are applied and every external symbol is bound to a `ret` stub. Any other relocation raises instead of guessing.
   - `machine` runs the image in Unicorn, as a program (`_start`, stdout, stderr, exit code) or as a function called the SysV way. Syscalls are an allow-list (read fd 0, write fd 1 and 2, getpid, exit, exit_group); everything else stops the run. An instruction cap and a wall-clock timeout bound it.
   - In function mode the machine reports the V4 kinds: `misaligned_call`, `callee_saved_clobber` (canaries in rbx, rbp, r12-r15), `unbalanced_stack` and `df_left_set`.
   - `abi_static` reports the V3 kinds with Capstone, relocations and section names: `missing_gnu_stack`, `pie_absolute_reference`, `syscall_clobber`, `red_zone_write`.
2. **The corpus is the test.** `tests/unit/emulator/test_abi_corpus.py` assembles every snippet of both dialects (nasm, gas-intel), requires the bad one to be flagged for its kind and the good one to produce nothing: 100% detected, 0 false positives (invariant: the corpus stays at 100%).
3. **A behavior gate** (`verification/behavior_gate.py`) assembles a program, relocates it, runs `_start` in the emulator and compares stdout and exit code with an `Expectation`. `chunked run --expect-stdout/--expect-exit` uses it as the oracle: a mismatch is a `fail` verdict whose reason goes to the model in the repair loop, and memory is written only after a pass.

## Not decided here

- Registering V3/V4 in the ladder (`native-asm` family): the registry runs checks on linked workspaces in `bart-tc`; this library works on objects. Wiring it needs the check contract to carry an object path (follow-up issue).
- Win64 (shadow space, `.pdata`), AVX (Unicorn rejects 256-bit VEX; route to V5), DWARF line mapping for faults, contract-driven import mocks, and running the emulator in a child process with a kill timeout (the timeout and instruction cap exist now).
- Unicorn's licence: the source tree says GPLv2, PyPI says BSD (roadmap F-6/F-48, #70). The licence check stays open before anything ships.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Link with `ld` first, then emulate the ELF | No linker on the Windows host; the object loader needs about 150 lines and no extra tool |
| QEMU user mode | Heavier, no per-instruction hooks for canaries and alignment checks |
| Run V4 for every kind | The corpus names which kinds need execution; V3 is faster for the rest |
| Keep behavior checks only in the sandbox (V5/V6) | They need Docker or WSL; the emulator works on any host and in unit tests |

## Consequences

- The behavior gate gives `chunked run` a real correctness check for single-file `_start` programs; it does not cover libc, threads, sockets or SIMD beyond what Unicorn runs.
- CI installs `nasm` so the corpus and gate tests run in the `python` job.
- Architecture §13.1 gains a pointer to this ADR; the ladder wiring is a roadmap follow-up.
