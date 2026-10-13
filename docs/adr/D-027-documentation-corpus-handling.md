# D-027: Documentation corpus handling

- Status: Proposed
- Date: 2026-10-13

## Decision

asm_doc/ holds the local manuals. The owner committed it to git on 2026-10-13 (not yet pushed); check the licenses in docs/knowledge-sources.md before publishing (GFDL binutils docs, Microsoft CC-BY-4.0 MASM docs, fasm docs with unclear terms). knowledge/sources.yaml records the URL, version, license and sha256 of each source.

Sources:
- MASM: ingest from the MicrosoftDocs cpp-docs Markdown (CC-BY-4.0), with pypdf as a fallback in an optional extra.
- NASM: from nasmdoc.txt by regex.
- fasm and binutils: from HTML via BeautifulSoup and lxml, with section allow-lists.

PyMuPDF (AGPL-3.0) is excluded from the product, which is BSD-2.

P0 additions: rule cards, ABI rows, syscall_64.tbl, instruction tables (Opcodes/asmjit).

## Rationale

Licenses are mixed: GFDL, BSD, Microsoft and CC-BY.

The docs cover assemblers but not instruction semantics or ABIs.

Structural chunking and fact extraction need clean sources.

## Alternatives considered

- Keep `asm_doc/` untracked (gitignored): proposed in the first draft; the owner chose to commit it instead. Revisit before publishing (roadmap open decision 7).
- Bulk-ingest the Intel SDM or Agner Fog: licensing forbids mirroring; link only.
