# D-007: The verification ladder is the judge; Definition of Done is set per story kind and target

- Status: Proposed
- Date: 2026-10-13
- Amended by: D-056

## Decision

Ladder:

- V0 syntax
- V1 assemble + nm vs registry
- V2 link
- V3 Capstone static ABI lint
- V4 Unicorn unit tests + dynamic ABI contract
- V5 C harness
- V6 golden I/O / qemu
- V7 trace on failure
- V8 Windows Sandbox (opt-in)

The T (tamper) and M (minimality) gates run after every apply.

The Definition of Done (DoD) table is set per story kind and target. The ABI mutation corpus must reach 100% detection with 0 false positives before agent output is trusted.

LLM review is advisory only.

## Rationale

Assembly has cheap, deterministic judges. Self-correction without external feedback fails, and sampling pays off when an automatic checker exists.

Unicorn runs in-process with exact PC-to-line mapping and catches ABI violations that tests miss: callee-saved registers, alignment, red zone, DF, shadow space.

## Alternatives considered

- LLM reviewer or "dry run" as a gate (draft): unreliable.
- C harness only: misses ABI violations that happen not to crash.
