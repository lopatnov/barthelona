# D-040: Compile-down strategy: compile C/Rust to assembly as an alternative `implement_symbol` path

- Status: Proposed
- Date: 2026-10-16

## Context

Aleksandr proposed a variant of the code-generation pipeline where the LLM writes a
higher-level language (C, Rust, etc.), the compiler produces the assembly listing
(`gcc -S`, `clang -S`), and the assembly is used as the initial patch, replacing or
supplementing the direct LLM-writes-assembly path.

The motivation: the compiler handles register assignment and calling-convention details,
reducing the most common hallucination failure mode, while the LLM focuses on semantics
it reasons about more reliably (C/Rust logic). Trade-off: pure AI-driven low-level
optimization is replaced by compiler-chosen code, which may be suboptimal for the
barthelona use case.

**Prior art:**
- Meta LLM Compiler (Meta AI, arXiv:2407.02524, July 2024): 7B/34B/70B models
  fine-tuned on LLVM IR and assembly for optimization, decompilation and flag tuning;
  shows specialized models outperform general LLMs on asm-level tasks by wide margins.
- STOKE / LENS (Stanford, 2016–2019): stochastic superoptimization; LLM-guided
  search replaces the random sampler in more recent work.
- Compiler Explorer (Godbolt, https://godbolt.org): instant compilation to asm for
  hundreds of compilers; useful as a development tool and for offline exploration.

**Papers provided by Aleksandr for further study** (HF paper IDs; all unreachable from
this container's network; to be read from the owner's machine):
- 2610.17953 (Oct 2026)
- 2505.11480 (May 2025)
- 2603.08706 (Mar 2026)
- 2605.21470 (May 2026)

**Infrastructure already in place:**
- The `bart-tc` Docker container (D-006) ships gcc, binutils and make.
  `gcc -O2 -S` and `clang -O2 -S` run inside the container with `--network none`.
- A `FileWrite{path, content}` patch is how assembly is already delivered.
- The full verification ladder (V0–V8) runs on any assembled source file
  regardless of how it was produced.

## Decision

Record the compile-down approach as a **Phase 2 experimental node type** named
`compile_high_level`, not as a core architecture change.  No action in Phase 0 or 1.

The node would:
1. Receive a `Symbol` spec, its `ContractRegistry` entry and the target preset.
2. Prompt the LLM for a C function (or Rust `extern "C"` function) that satisfies
   the contract (same inputs/outputs, same ABI), with a hard token cap.
3. Write the C source to a temp path inside the workspace under `bart-tc`.
4. Run `gcc -O2 -S [-masm=intel] -o <symbol>.s <symbol>.c` (or clang equivalent)
   inside the bart-tc container via the WSL agent.
5. Return the `.s` content as a `FileWrite` patch for the symbol's source file.
6. The normal verification ladder then runs on the assembled output.

The node is **gated by the Phase 2 benchmark**: it is enabled for a profile only if the
bench shows a gain over the direct-codegen path or the `candidates` node.

## Rationale

1. **Infrastructure-zero**: gcc is already in `bart-tc`.  No new container image, no
   network access needed; the sandbox policy (D-010, Invariant 2) is fully respected.
2. **Oracle-decides principle preserved** (Invariant 1): the compiler itself is not an
   oracle; the assembler + linker + V3/V4 ABI checks remain the judges.
3. **Fits the topology DSL** (D-004, D-028): `compile_high_level` is a registered
   node type, can appear in a slot in the `module_create`/`implement_symbol` template,
   and its output is a normal `apply_patch` → `ladder` sequence.
4. **Reduces the hardest hallucination mode**: direct LLM asm-codegen fails most often
   on register allocation and ABI bookkeeping; the compiler handles those.
5. **Complementary to the retro and lesson system**: if compiler output has an
   unwanted pattern (e.g. verbose preamble), a lesson can capture a clean-up heuristic.

## Constraints and open questions

- **Dialect mismatch**: GCC and Clang produce GAS syntax (AT&T by default;
  `-masm=intel` switches to Intel syntax on x86).  NASM targets would receive GAS
  output, which has different directives and label syntax.  For NASM presets this node
  produces GAS output that is incompatible with NASM sources as written; two workarounds:
  (a) compile the generated .s with `as`/`ld` instead of nasm (i.e. treat it as a GAS
  module even for a "NASM project"), or (b) run `objdump -M intel` on the compiled
  binary and convert.  **Decision needed before implementing**: which workaround, or
  skip NASM for v1 of this node.
- **Verbose preamble**: compiler output includes `.cfi_*` directives and often a full
  frame setup that bare-metal assembly avoids.  The node should apply a configurable
  strip pass (remove `.cfi_*`, optionally strip the frame, keep the core instructions).
- **Second failure mode**: the LLM must generate valid C/Rust; that is a different but
  real failure surface.  The fix loop still applies; C errors are usually more
  diagnostic than asm errors.
- **Godbolt API** is useful for manual exploration during development but cannot be
  used from `bart-tc` (no network, D-010).  Use local gcc/clang.
- **Benchmark gate**: do not enable by default; enable only after a paired comparison
  on the Phase 2 holdout split shows a gain over the direct path whose interval
  excludes zero at the bench size (a fixed 5-point margin is below what a 20 to 60
  task bench can detect; plan review 2026-10-17, #101). The Phase 0 bake-off measures
  a C-then-`gcc -S` arm first (#100).

## Alternatives considered

- **Direct LLM asm only** (status quo): harder for the model on ABI correctness; but
  produces idiomatic output for the target dialect.
- **LLM-guided superoptimization** (STOKE-style loop inside the agent): expensive,
  slow; deferred to Phase 5 Policy Lab exploration.
- **Compiler Explorer REST API**: requires network from the sandbox; rejected (D-010).
- **Fine-tuned assembly model** (Meta LLM Compiler-style): useful but requires a
  specialized model that may not be in the local roster; deferred to Phase 5.

## Consequences

- Adds a Phase 2 roadmap item: design and implement `compile_high_level` node type.
- Requires one owner decision before implementing: dialect strategy for NASM presets.
- No changes to contracts, policies or the verification ladder.
- `TargetProfile.dialect` drives which path is offered; GAS presets are first candidates.
