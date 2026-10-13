---
name: add-dialect
description: Step-by-step checklist for adding a new assembler dialect or target preset (e.g. FASM ELF64/PE64, Win64 via mingw, asmc/UASM, ml64, AArch64) to barthelona without breaking verification guarantees.
disable-model-invocation: true
argument-hint: "<dialect-id> <preset-id>"
arguments: [dialect, preset]
---
# Add dialect `$dialect` / preset `$preset`

Read first: `docs/architecture.md` §12 (toolchain layer), §13 (ladder and DoD), §15.1 (contract codegen), and ADR D-021. Work through the steps in order, with tests for each:

1. **Decision.** If the preset needs a new executor or image (wine, qemu-user, windows-native), write an ADR first (`/new-adr`).
2. **Toolchain image.** Add the packages to `docker/toolchain/Dockerfile` or a new image, rebuild, and run `barthelona probe`. Pin versions; record them in `config/toolchains.lock.json`.
3. **Capture real diagnostics before writing the parser.** Assemble known-bad files and save the real stdout/stderr in `tests/fixtures/diagnostics/<tool>/<version>/`. FASM reports frames (`file [line] macro [mline]:` then `error:`) and only the first error, so it needs a state machine.
4. **`Dialect` implementation** (`src/barthelona/toolchains/dialects/$dialect.py`): `syntax_check`, `assemble`, `preprocess`, `parse` (→ `Diagnostic` with `error_sig`), `includes` (needed for the include/incbin/`file` fence), local-label regex, `render_interface`, `render_stub`.
5. **Codegen** for export/import syntax, structs and consts. Add golden files in `tests/codegen_golden/$dialect/`. An all-stub skeleton must build.
6. **Preset** in `config/targets.yaml`: arch, OS, ABI, object format, link mode, `run_env`, and the DoD per story kind.
7. **ABI facts.** Add or extend `knowledge/abi/<abi>.yaml`, cited from the psABI or Microsoft docs.
8. **Mutation corpus.** Add good/bad pairs in `tests/abi_mutation/$dialect/` for every applicable violation kind. V3/V4 must stay at 100% detection and 0 false positives.
9. **Rule card** `knowledge/rulecards/$dialect-<target>.md`, about 400 tokens: boilerplate, import/export, calling convention, alignment, syscalls, pitfalls. Verify it against `asm_doc/` with the `asm-docs` skill.
10. **Knowledge.** Add the dialect's docs to the sources manifest and the directive index (`docs/knowledge-sources.md`).
11. **Bench.** At least 5 tasks for the preset, in both `dev` and `holdout`.
12. **UI.** The preset appears in New request, and is greyed out with a reason when the resolver cannot satisfy it.
13. **Docs.** Add `docs/dialects/$dialect.md` (flags, diagnostics formats, quirks), and update `docs/architecture.md` §12–§13 and `docs/roadmap.md`.

Exit criteria (from the roadmap): the conformance kit passes, and at least 5 bench tasks are solved within budget.
