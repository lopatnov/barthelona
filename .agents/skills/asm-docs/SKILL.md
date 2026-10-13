---
name: asm-docs
description: Look up facts in the local assembler documentation in asm_doc/ (NASM 3.02 manual and instruction list, flat assembler 1.73 / fasmg manuals and Win32 headers, GNU as and ld (binutils 2.47), MASM reference PDF) instead of relying on memory. Use when writing or reviewing assembly, rule cards, diagnostics parsers or dialect adapters, or when the user asks how a directive, instruction form, macro feature, register or linker-script command works.
when_to_use: Any question about NASM/FASM/GAS/MASM/ld syntax, directives, macros, instruction operand forms, output formats, or linker scripts.
argument-hint: "[dialect] [topic]"
---
# Assembler documentation lookup

The docs live in `asm_doc/`, a read-only local copy tracked in git (licenses: `docs/knowledge-sources.md`). Prefer **exact sections** over memory. Cite what you used as `[NASM 3.02 §5.3]`, `[fasm manual 2.3.3]`, `[as #i386_002dRegs]`, `[ld #MEMORY]` or `[MASM PDF p.N]`.

## Helper

`extract.py` prints one section as plain text, capped at 400 lines; use `--max N` to change the cap. Run it from the repo root through the env wrapper: `.\scripts\dev.ps1 python ...` in PowerShell, or `scripts/dev.sh python ...` in bash. The examples below are shortened to `python ...`:

```
python .claude/skills/asm-docs/extract.py nasm-toc                 # NASM section map with line numbers
python .claude/skills/asm-docs/extract.py nasm 5.3                 # NASM section (chapter "13", "F.1.1", ...)
python .claude/skills/asm-docs/extract.py insn MOVZX               # NASM Appendix F operand forms + CPU flags
python .claude/skills/asm-docs/extract.py ids fasm/manual.htm      # anchor ids of an HTML manual
python .claude/skills/asm-docs/extract.py html fasm/manual.htm 2.3.3
python .claude/skills/asm-docs/extract.py html binutils/as.htm i386_002dRegs
python .claude/skills/asm-docs/extract.py html binutils/LD.htm MEMORY
```

## Map

| Dialect / tool | File | Useful anchors |
| --- | --- | --- |
| NASM 3.02 | `nasm-3.02-xdoc/doc/nasmdoc.txt` | Ch. 3 language, 4 quirks, **5 preprocessor**, 6 standard macros, **8 directives**, **9 output formats**, 11 32-bit code, **13 64-bit code**, 14 troubleshooting, App. A warning classes, **App. F instruction list** (use `insn`) |
| flat assembler 1.73 | `fasm/manual.htm` | 1.1 overview, 1.2 syntax, 2.1 x86 instructions (2.1.1–2.1.25), **2.2 control directives**, **2.3 preprocessor** (2.3.3 macroinstructions), **2.4 formatter** (MZ/PE/COFF/ELF) |
| fasmg | `fasm/fasmg_manual.htm`, `fasm/fasmg.htm` (FAQ) | use `ids` |
| FASM Windows headers | `fasm/win32.htm` | structures, imports, proc32/proc64, exports, COM, resources |
| GNU as | `binutils/as.htm` | `Pseudo-Ops` (all directives), `i386_002dDependent`, `i386_002dSyntax`, `i386_002dMnemonics`, `i386_002dRegs`, `i386_002dMemory`, `i386_002dJumps`, `i386_002dDirectives`, `AArch64_002dDependent` |
| GNU ld | `binutils/LD.htm` | `Scripts`, `SECTIONS`, `MEMORY`; invocation options via `ids` |
| binutils tools | `binutils/binutils.htm` | objdump, nm, readelf, objcopy |
| MASM | `masm/cpp-assembler-msvc-170.pdf` (475 pages) | Read the first pages for the TOC, then read the directive's pages with the Read tool (`pages: "N-M"`, at most 20 per call). Error messages (A1000…) are near the end. |

For quick keyword searches, use Grep on the file, e.g. pattern `%macro` in `nasmdoc.txt`, or `\.cfi_` in `as.htm`. Then extract the section that contains the hit.

## Rules

- `asm_doc/` is read-only. Never edit or reformat it.
- For calling-convention facts (SysV psABI, Microsoft x64), syscall numbers or instruction semantics, these local manuals are not authoritative. Use the sources in `docs/knowledge-sources.md` (via the `docs-researcher` agent) and cite URLs.
- The local NASM docs are for 3.02; Ubuntu's apt nasm is 3.01. Mention version differences when they matter.
