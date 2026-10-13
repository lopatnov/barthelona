# D-008: The contract registry is the single source of truth; interface files are generated

- Status: Proposed
- Date: 2026-10-13

## Decision

contracts.yaml holds every symbol's registers, flags, clobbers, stack and memory effects.

header_gen produces all of the following, committed and hash-headed:
- per-module .inc files
- stubs
- contracts.h
- C harnesses
- emulator mocks and fixtures
- the Makefile

LLMs never write extern/global declarations or build files.

## Rationale

This is the core of the Gemini draft that survived the audit (interface registry, generated .inc files, mock stubs). Making it the single source removes the drift between modules that small models cause.

Generated stubs let modules link and be tested before their dependencies exist.

## Alternatives considered

- A prose ABI document plus LLM-written headers (draft): drifts.
- Per-module agreements in prompts: unverifiable.
