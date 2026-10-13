---
paths:
  - "src/barthelona/knowledge/**"
  - "src/barthelona/memory/**"
  - "knowledge/**"
  - "docs/knowledge-sources.md"
---
# Knowledge and memory rules (docs/architecture.md §14–§15, docs/knowledge-sources.md, ADR D-016, D-017, D-027)

- Retrieval order:
  1. Exact facts from SQLite (`insn_forms`, `insn_ref`, `directives`, `diagnostics`, `syscalls`, `abi_conventions`), keyed by tokens extracted with regex.
  2. FTS5 BM25 over doc chunks.
  3. Qdrant hybrid search (dense + sparse, RRF), only after the retrieval eval (≥60 golden queries, recall@5 / MRR) shows a gain.
- Chunking:
  - split by structure;
  - ≤480 tokens per chunk;
  - code blocks and tables kept whole;
  - a breadcrumb prefix on every chunk;
  - `parent_id` for expansion.
- The keyword tokenizer keeps sigils: `unicode61 tokenchars '%.@$_#'`.
- Every source is registered with URL or path, version, license, parser and sha256. Never mirror sources without a clear license (felixcloutier, uops.info, Agner Fog, Intel/AMD manuals): link to them instead. No AGPL parsers (PyMuPDF).
- nomic embeddings need the `search_document:` / `search_query:` prefixes. LM Studio and FastEmbed vectors are not interchangeable.
- Qdrant runs in WSL docker and is reachable only while the VM runs. Use `qdrant-client` pinned to the server's minor version. The Qdrant MCP server is a development aid only.
- Lessons are evidence-gated:
  - created only from a fail→pass transition with the diff attached;
  - keyed by scope and normalized `error_sig`;
  - promoted candidate → active (regression check passes) → approved (human);
  - injected only if the bench shows a gain.
