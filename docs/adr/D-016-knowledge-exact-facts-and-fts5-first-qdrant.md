# D-016: Knowledge: exact facts and FTS5 first; Qdrant hybrid only after the retrieval eval

- Status: Proposed
- Date: 2026-10-13

## Decision

facts.sqlite holds:
- NASM App F instruction forms
- directive indexes
- diagnostic codes
- syscall_64.tbl
- ABI conventions
- instruction references

Lookup is by regex-extracted keys.

MVP docs search: SQLite FTS5 BM25 over structural chunks (≤480 tokens, with breadcrumbs), using a sigil-preserving tokenizer.

Phase 3 adds Qdrant hybrid search behind the Retriever interface:
- nomic v1.5 dense vectors + client-side asm-aware sparse vectors, fused with RRF;
- enabled only if the retrieval eval shows a gain;
- only after Qdrant storage moves off the /mnt/c bind mount.

Rule cards are always injected.

## Rationale

Mnemonics, directives and error codes are exact tokens, so BM25 and exact lookup win.

FTS5 needs no running service. Qdrant answers only while the WSL VM is up, and its bind-mount storage risks data loss.

The RAM budget is tight.

## Alternatives considered

- Qdrant from day one (draft): an extra moving part with no measured gain.
- Vector-only search: misses exact tokens.
- Qdrant's server-side bm25: strips sigils and stems by default.
