# D-022: Language policy

- Status: Proposed
- Date: 2026-10-13

## Decision

Users can write requests in Russian, Ukrainian or English.

intake normalizes each request to an English goal. All internal artifacts, prompts, code comments, docs and the UI are in English. The normalized spec is shown for approval.

## Rationale

The user asked for English documents and conversation, while allowing Russian input.

English specs improve retrieval (the English nomic v1.5 embedder) and model performance.

## Alternatives considered

- A bilingual UI: more work for little value.
- The multilingual nomic v2-moe embedder: 512-token cap; only if Russian text must itself be searched.
