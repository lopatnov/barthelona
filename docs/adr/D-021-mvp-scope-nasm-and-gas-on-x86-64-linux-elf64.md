# D-021: MVP scope: NASM and GAS on x86-64 Linux ELF64 SysV

- Status: Proposed
- Date: 2026-10-13

## Decision

MVP presets: linux-x64-{nasm, gas-intel, gas-att}-{static, libc}.

In scope: create mode, plus edit mode for barthelona-created projects.

Deferred:
- FASM, Win64 (mingw+wine), ELF32, MASM-compatible assemblers, ml64, boot: Phase 4; ARM/RISC-V: Phase 5
- importing external repos: Phase 3

The UI shows deferred presets disabled, with the reason.

## Rationale

These are the best-supported toolchains, with apt packages in the image and DWARF for line mapping.

The gcc C harness is available.

MASM needs admin-installed VS Build Tools. FASM has no DWARF line mapping and reports only its first error.

## Alternatives considered

- FASM/KolibriOS first (the draft's emphasis): weaker oracles and a higher setup cost.
- MASM first: needs Windows admin rights.
