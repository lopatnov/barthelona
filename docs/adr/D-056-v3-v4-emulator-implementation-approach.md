# D-056: V3/V4 Emulator Implementation Approach

- Status: Proposed
- Date: 2026-10-24
- Amends: D-007, D-046

## Context

The verification ladder (§13.1) defines V3 (static ABI lint) and V4 (Unicorn dynamic ABI checks) as Phase 2 deliverables. The Unicorn engine source is available in `.reference/unicorn/` (GPLv2 per `COPYING`, though PyPI metadata says BSD — see roadmap F-6/F-48). The Python bindings in `.reference/unicorn/bindings/python/` provide a clean API for x86-64 emulation.

**Current state (Phase 0):**

- V0-V2 implemented in `src/barthelona/verification/native_asm.py`
- V5-V6 implemented in `src/barthelona/verification/harness.py` and `golden.py`
- V3/V4 not implemented — the "emulator child" process exists only in architecture diagrams

**Architecture requirements (§13.1):**

- V3: Static ABI lint over Capstone CFG (emulator child, <1 s)
- V4: Unicorn unit tests + dynamic ABI contract checks (emulator child, 10–500 ms/case)
- V4 runs **only for mutation-corpus kinds that V3 + V5 canary cannot detect** (#102)
- Emulator child: Windows child process, killed on timeout, contains `unicorn` + `capstone` (SDK containment, §132)

**ABI mutation corpus** (`tests/abi_mutation/`) has 8 kinds × 2 dialects × good/bad snippets. V3/V4 must flag 100% of bad with 0 false positives on good.

## Decision

### V3: Static ABI Lint (Capstone CFG)

1. **New package**: `src/barthelona/emulator/` (emulator child package)
2. **Capstone** for CFG construction and static analysis
3. **Checks** (from §13.1):
   - RSP delta along every path; stack balanced at every `ret`
   - Alignment ≡ 8 (mod 16) at every `call`
   - Callee-saved registers saved/restored (SysV: rbx, rbp, r12–r15)
   - Reads of rcx/r11 after `syscall`
   - Absolute 32-bit references in PIE code
   - `.note.GNU-stack` present
   - `vzeroupper` before returning from AVX code
   - Win64 (later): shadow space ≥ 32 bytes, `.pdata` entry per non-leaf function
4. **Output**: Diagnostics with `file:line` via DWARF (`-g -F dwarf` for NASM, `-g` for GAS)

### V4: Dynamic ABI Checks (Unicorn)

1. **Same package**: `src/barthelona/emulator/`
2. **Unicorn** (Python bindings) for x86-64 emulation
3. **Per architecture §13.1 "How V4 works":**
   - Link module at fixed base in `bart-tc` (`ld -Ttext=… --defsym <import>=<trap>`), load segments with `pyelftools`
   - Stack with guard pages; on entry `rsp ≡ 8 (mod 16)`, return address → trap
   - Canaries in callee-saved registers (SysV: rbx, rbp, r12–r15; Win64: +rdi, rsi, xmm6–15)
   - Hooks:
     - Calls: alignment at each call site (Capstone pre-pass), Win64 shadow space
     - Memory writes: red zone, return-address slot, outside declared buffers
     - Syscalls/interrupts: allow-list only — `write` → captured stdout, `exit`
   - Imports served by Python mocks from registry (the "mock stubs between sprints")
   - Limits: instruction-count cap, microsecond timeout
   - Error mapping: faulting PC → `file:line` via DWARF
   - AVX: Unicorn rejects 256-bit VEX; route to V5 (setup probe confirms)
4. **Only enabled** for mutation-corpus kinds where V3 + V5 canary miss (roadmap #102)

### Package Structure

```
src/barthelona/emulator/
├── __init__.py
├── static_lint.py      # V3: Capstone CFG analysis
├── dynamic_check.py    # V4: Unicorn emulation
├── elf_loader.py       # pyelftools segment loading
├── dwarf_map.py        # PC → file:line via DWARF
├── mocks.py            # Registry-driven import mocks
├── canary.py           # Callee-saved canary setup
└── hooks.py            # Unicorn hook callbacks
```

### Registration

- New target family checks registered via `CheckRegistry` (D-046)
- Family `native-asm` gets V3/V4 `LevelCheck` implementations
- `supports(ctx)` returns `Unsupported` if no `unicorn`/`capstone` or no DWARF

### Dependencies

- Add `unicorn` and `capstone` to `pyproject.toml` (optional extra `emulator`)
- Locked per-platform via `scripts/lock.ps1` (D-031)
- **License**: Confirm wheel's bundled license files before distributing binaries (F-48)

### Testing

- Property tests: every bad mutation-corpus snippet flagged, no good snippet flagged
- Integration tests (`-m wsl`): real images running known-bad projects

## Rationale

1. **Separate package** for SDK containment (D-045): `unicorn`/`capstone` only in `emulator/` — licence and supply-chain questions isolated.
2. **Capstone first (V3)**: Static analysis is faster, catches most ABI violations without emulation overhead. V4 only for the hard cases V3 misses.
3. **Unicorn bindings** are mature: the `.reference/unicorn/bindings/python/` provides `UcIntel` with x86-64 register access, syscall hooking, memory mapping — exactly what we need.
4. **DWARF mapping** reuses `-g -F dwarf` (NASM) / `-g` (GAS) already in presets.
5. **Mock stubs from registry**: The `ContractRegistry` already has `inputs`, `outputs`, `clobbers`, `mem_effects` — perfect for generating Python mocks.
6. **Separate child process**: Architecture §3 requires it ("Emulator child | Windows child process | V3 lint and V4 emulation. Killed on timeout.") — prevents crashes from taking down the engine.

## Alternatives Considered

| Alternative                           | Rejected Because                                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Keep unicorn in `verification/`       | Violates SDK containment (D-045); mixes GPL-tainted code with BSD-2 product                            |
| Use QEMU user-mode instead of Unicorn | Heavier, no fine-grained hook API, harder to inject canaries/mocks                                     |
| Run V4 for all cases                  | Wasteful; V3 + V5 canary catch most; roadmap #102 explicitly says "only for kinds V3 + V5 canary miss" |
| Skip V3, only V4                      | Static lint is <1 s and catches 80%+; skipping loses fast feedback                                     |

## Consequences

- **New dependency extra**: `emulator` in `pyproject.toml` (opt-in until Phase 2)
- **New tests**: Mutation corpus assertions in Phase 2 exit criteria (roadmap §83)
- **Architecture updates**: §13.1 V3/V4 details, §3 emulator child row, §132 SDK containment row
- **Roadmap**: Phase 2a deliverables become concrete
- **License review**: Must verify unicorn wheel license before any distribution (F-48)
