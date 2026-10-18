# D-055: Disassembly is a licence-gated input and aid, never an oracle

- Status: Proposed
- Date: 2026-10-18
- Amends: D-019, D-040

## Context

The owner allows disassembly (2026-10-18). Today it exists only inside the product's internals: Capstone drives the V3 CFG lint and the emulator child (D-045), `nm` plus Capstone recover inferred contracts in edit mode (D-019), and `objdump -M intel` is an unresolved workaround for NASM compile-down (D-040, open decision 12, F-84). No tool, input path, repair aid or training use is defined, and nothing says which binaries may be disassembled (#180).

Prior art:
- Capstone is a BSD-licensed disassembly library already pinned in `pyproject.toml` and NOTICE.md; `objdump` ships with binutils in `bart-tc`.
- Compile-down (D-040) already treats compiler output as an input; disassembly extends the same idea to binaries.

## Decision

1. **Allowed uses.**
   - *Input:* disassembly of gcc/clang output and of binaries whose licence permits derivative works, as the source for porting or re-implementing a routine (edit mode, compile-down).
   - *Aid:* disassembly of the system's own build as evidence in repair prompts (what the assembler actually emitted), and in diffs between expected and actual behavior.
   - *Training data:* only with a licence-checked manifest entry (repo, commit, path, licence, hash; #171, F-17).
2. **Never an oracle.** Disassembly output does not accept work. Round-trip checks (assemble the disassembly and compare) may be a V-level check, but only when registered as such (D-046).
3. **Licence gate.** Disassembling a binary is deriving from it. The input path requires a recorded licence that allows it; proprietary or unknown licence means refuse, with a diagnostic naming the missing record. Clean-room reference to behavior (tests, RFCs) is preferred over reading code.
4. **Tools are registry entries.** `objdump` and a Capstone-based dumper are registered tools (D-053, #175), run in `bart-tc` with no network; their output is data in prompts, not instructions.
5. **Dialect.** For NASM presets, disassembly is emitted in Intel syntax and treated as reference text, not as source to assemble; the dialect question for compile-down (F-84) stays separate.

## Rationale

Disassembly is valuable evidence for a model that otherwise guesses what its output became, and for porting. It is also a licence and correctness risk if treated as authority, so it is gated and kept advisory (invariant 1).

## Alternatives considered

- **Forbid disassembly of anything external.** Safe, but loses compile-down inspection and edit-mode recovery.
- **Allow everything.** Licence exposure and no provenance.

## Consequences

- `docs/knowledge-sources.md` gains a binary-input licence rule when the tool lands.
- Implementation rides on the tool registry (#175) and the corpus manifest (#171); roadmap F-88 tracks it.
