# Knowledge sources

Where barthelona's assembler knowledge comes from, what is already on disk, and what to add.
Design of the knowledge layer: `docs/architecture.md` §14. Decision: `docs/adr/D-016`, `D-027`.

Rules:
- `asm_doc/` holds the local manuals and is tracked in git (owner decision, 2026-10-13). It has mixed licenses (GFDL / BSD / Microsoft / fasm), so review them before publishing the repo (`docs/roadmap.md`, open decision 7). Priorities below (P0–P3) are importance, not project phases. The machine-readable manifest `knowledge/sources.yaml` (URL, version, license, parser, sha256) arrives in Phase 1; this page is its human-readable counterpart.
- Exact facts (instruction forms, directives, syscalls, ABI rows) go into SQLite tables and are looked up by key. Vector or keyword search is for prose only.
- Never bulk-mirror sources without a clear license (felixcloutier, uops.info, Agner Fog, Intel/AMD manuals): link to them, or ingest locally for personal use without committing.

## 1. Already in `asm_doc/` (verified 2026-10-13)

| Document | What it is | Use | How to ingest |
| --- | --- | --- | --- |
| `nasm-3.02-xdoc/doc/nasmdoc.txt` | NASM 3.02 manual: 392 numbered sections; App. F is the instruction list (~6.8K `MNEMONIC operands CPU-flags` rows) | Ch. 1–14 and App. A–B as prose; App. F into `insn_forms`; drop App. C (version history) | Regex heading splitter on the `.txt` (cleaner than HTML); HTML chapter files only for deep links |
| `fasm/manual.htm` | flat assembler 1.73 manual: instructions, control/preprocessor/formatter directives (MZ/PE/COFF/ELF) | All; §2.2–2.4 headings into the `directives` table | Split by `<h4>`, keep `<pre>` whole, tables → Markdown |
| `fasm/fasmg_manual.htm`, `fasmg.htm` | flat assembler g manual and FAQ | All, tagged `dialect=fasmg` | Split by `<h2>`/`<h3>` |
| `fasm/win32.htm` | FASM Windows headers manual (structures, imports, proc32/64, COM, resources) | High value for FASM Windows targets | Split by `<h3>` |
| `fasm/design.htm`, `ufasm.htm` | Essays | Low priority | Split on `<b>` titles |
| `binutils/as.htm` | "Using as" (binutils 2.47): ~60 architectures; 118 pseudo-op sections | Keep Invoking, Syntax, Sections, Symbols, Expressions, Pseudo-Ops, **i386**, AArch64, RISC-V; drop other arches | Allow-list by section id; pseudo-op headings into `directives` |
| `binutils/LD.htm` | GNU ld manual | Linker scripts + selected invocation options | Split by section |
| `binutils/binutils.htm` | objdump, objcopy, readelf, nm | For verifier work only | Split by tool |
| `binutils/bfd.htm`, `ctf.htm`, `gprof*.htm`, `sframe-spec.htm` | Internals | Skip | — |
| `masm/cpp-assembler-msvc-170.pdf` | MASM reference (MS Learn export, 475 pages): 180 directives, 73 operators, 61 error messages | All, but prefer the Markdown source below | One chunk per TOC leaf; error codes into `diagnostics`. Avoid PyMuPDF (AGPL); use `pypdf` if needed |

## 2. Better or missing sources, by priority

| Priority | Source | Why | License / note | URL |
| --- | --- | --- | --- | --- |
| P0 | Hand-written **dialect rule cards** (~400 tokens each: nasm-linux-x64, gas-intel/att-linux-x64; later fasm, masm, win64) | Always injected; the highest-value context per token | Own content | `knowledge/rulecards/` (Phase 1) |
| P0 | Microsoft x64 calling convention | Win64 ABI row + chunks | CC-BY-4.0 (docs) | https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention |
| P0 | System V AMD64 psABI | SysV ABI row (hand-curated summary) | License unclear: summarize, don't mirror | https://gitlab.com/x86-psABIs/x86-64-ABI |
| P0 | Linux `syscall_64.tbl` + signatures (systrack) | `syscalls` table | Kernel GPL-2.0 (factual data) | https://github.com/mebeim/systrack , https://github.com/mebeim/linux-syscalls |
| P0 | Machine-readable x86 instruction data: Opcodes `x86_64.xml`; asmjit `isa_x86.json`; Go `x86.csv` | `insn_ref` (Intel/AT&T names, operand read/write, implicit registers, ISA extension) | Opcodes: check LICENSE; asmjit: Zlib; Go: BSD | https://github.com/Maratyszcza/Opcodes , https://github.com/asmjit/asmjit (db/isa_x86.json), https://pkg.go.dev/golang.org/x/arch/x86/x86csv |
| P1 | FASM Windows package: `INCLUDE/` (win64a.inc, proc64 macros) + `EXAMPLES/`; fasm2 | Macro index and example code for FASM targets | BSD-style | https://flatassembler.net/download.php |
| P1 | **MicrosoftDocs/cpp-docs MASM Markdown** | Replaces the MASM PDF: one file per directive, clean text | CC-BY-4.0 / MIT | https://github.com/MicrosoftDocs/cpp-docs |
| P1 | microsoft/win32metadata | Windows API signatures for a `winapi` table | MIT | https://github.com/microsoft/win32metadata |
| P1 | felixcloutier.com x86 reference | Deep links in answers and rule cards | Unofficial, no license: links only | https://www.felixcloutier.com/x86/ |
| P1 | Intel SDM; AMD APM vol. 3 | Optional personal local ingestion | Vendor terms: never commit | https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html , https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/24592.pdf (APM; vol. 3 is pub. 24594) |
| P1 | KolibriOS `sysfuncs.txt` + `macros.inc` | Only if KolibriOS becomes a target | GPL | https://git.kolibrios.org/KolibriOS/kolibrios |
| P2 | uops.info `instructions.xml` | Latency/ports for a future optimizer role | No license stated: personal use | https://uops.info/xml.html |
| P2 | Agner Fog optimization manuals | Links only | Copyrighted | https://www.agner.org/optimize/ |
| P2 | OSDev wiki | On-demand, gated research only | Mixed (CC0 only after 2011) | https://wiki.osdev.org/ |
| P3 | Arm AARCHMRS Instructions.json; RISC-V ISA manual + riscv-opcodes | Architecture expansion | Check notices; RISC-V manual CC-BY-4.0 | https://github.com/riscv/riscv-isa-manual |
| P3 | asm-lsp `docs_store` | Cross-check of the directive index (gas, nasm, masm, fasm) | BSD-2 | https://github.com/bergercookie/asm-lsp |
| — | Intel XED datafiles | Authoritative encodings if needed | Apache-2.0, heavy to parse | https://github.com/intelxed/xed |

## 3. Chunking rules (summary)

- Split by document structure first; a leaf of 450 tokens or less is one chunk. The hard cap is 480 tokens, so both local nomic embedding models stay usable.
- Keep code blocks and tables whole; about 10% overlap for prose only.
- Prepend a breadcrumb such as `[NASM 3.02 › 5 Preprocessor › 5.3 Multi-Line Macros]` to every chunk's indexed text.
- The keyword tokenizer keeps sigils: `%macro`, `.globl`, `@@`, `$` stay single tokens.
- Store `parent_id` so a large-context model can expand a chunk to its whole section.
