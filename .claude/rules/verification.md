---
paths:
  - "src/barthelona/verification/**"
  - "src/barthelona/contracts/**"
  - "tests/abi_mutation/**"
  - "tests/codegen_golden/**"
---
# Verification and contracts rules (docs/architecture.md §13, §15.1; ADR D-007, D-008, D-009)

- **Ladder:**

  | Level | Check | Where |
  | --- | --- | --- |
  | V0 | syntax | |
  | V1 | assemble + `nm` vs registry | |
  | V2 | link | |
  | V3 | Capstone static ABI lint | |
  | V4 | Unicorn unit tests + dynamic ABI checks | |
  | V5 | C harness | sandbox |
  | V6 | golden I/O | sandbox |
  | V7 | gdb/qemu trace, after a failure only | |
  | V8 | real Windows, opt-in | |

  Plus the tamper gate after every apply, and the minimality gate in edit mode. The DoD is set per story kind and target.
- **ABI facts** must come from `knowledge/abi/*.yaml` (cited from the SysV psABI and the Microsoft x64 docs), not from memory.
  - SysV callee-saved: rbx, rbp, r12–r15.
  - Win64 callee-saved additionally: rdi, rsi, xmm6–15.
  - At function entry, rsp ≡ 8 (mod 16).
- **V4 harness:**
  - guard pages on both sides of the stack;
  - canaries in callee-saved registers;
  - hooks for call-site alignment, red-zone/return-slot writes and allow-listed syscalls only;
  - registry-generated Python mocks for imports;
  - instruction and time caps;
  - DWARF mapping of faults to `file:line`;
  - AVX-256 routed to V5, because Unicorn does not support it.
- **Every new check** needs a good and a bad entry in `tests/abi_mutation/<dialect>/{good,bad}/`. The corpus must stay at 100% detection and 0 false positives.
- **`contracts.yaml` is the single source of truth.** `gen/` files are generated with a hash header and must regenerate byte-identically (tamper gate). Codegen changes update `tests/codegen_golden/` deliberately, in the same commit.
- **Frozen tests and contracts** are never edited by coding roles. Changes go through a `contract_change` story and gate G2.
