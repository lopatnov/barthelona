---
paths:
  - "tests/fixtures/asm/**"
  - "tests/abi_mutation/**"
  - "tests/codegen_golden/**"
  - "bench/**"
  - "knowledge/rulecards/**"
  - "docker/**/*.asm"
---
# Assembly sources in this repo (fixtures, mutation corpus, bench tasks, rule cards)

General:
- One dialect per directory (`.../nasm/`, `.../gas-intel/`, `.../gas-att/`, later `.../fasm/`, `.../masm/`). `.asm`, `.inc` and `.s` overlap across dialects, so never infer the dialect from the extension.
- Each file starts with a header comment stating the dialect, target preset and expected result (e.g. `; dialect=nasm preset=linux-x64-nasm-static expect=V6:pass`).
- Use LF line endings.
- Emit a `.note.GNU-stack` section (ld ≥ 2.39 warns otherwise).
- Respect the target ABI: SysV callee-saved rbx, rbp, r12–r15; rsp ≡ 8 (mod 16) at entry, so align to 16 before `call`; the red zone is 128 bytes below rsp (leaf functions only); after `syscall`, rcx and r11 are clobbered.
- Check facts in `asm_doc/` with the `asm-docs` skill instead of relying on memory, and cite the section.

NASM (`nasm -f elf64 -g -F dwarf -Xgnu`):
- Write `default rel` for RIP-relative data. For PIE/libc calls use `call fn wrt ..plt`.
- `section .note.GNU-stack noalloc noexec nowrite progbits`.
- Local labels start with `.`. Export with `global`, import with `extern`.

GAS (`as --64 -g --fatal-warnings`):
- Intel syntax needs `.intel_syntax noprefix` (destination first). AT&T is source-first with `%reg` and `$imm`.
- For functions use `.globl f` + `.type f, @function` + `.size f, .-f`. Local labels start with `.L`.
- `.section .note.GNU-stack,"",@progbits`.

Bench hidden tests (`bench/tasks/**/hidden/`) and the whole holdout split are never read into the conversation or into prompts.
