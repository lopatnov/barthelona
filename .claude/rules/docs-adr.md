---
paths:
  - "docs/**"
  - "AGENTS.md"
  - "CLAUDE.md"
  - "README.md"
---
# Documentation rules

- Write in English, concisely. `docs/architecture.md` is authoritative. When code and docs disagree, fix one of them in the same change.
- ADRs live in `docs/adr/D-NNN-slug.md` (use the `new-adr` skill).
  - Template sections: Context (optional), Decision, Rationale, Alternatives considered, Consequences (optional), Status, Date, Amends / Amended by.
  - Update `docs/adr/README.md` and the affected sections of `docs/architecture.md` in the same change.
- Cite a URL for every version-, price- or date-sensitive fact (model ids, prices, library APIs, tool versions), and say when it was checked.
- Never copy facts from `docs/archive/` (the Gemini brainstorm) without verifying them.
- Keep `AGENTS.md` (shared, canonical) and `CLAUDE.md` (imports it, Claude-only notes) under about 200 lines together. They point to docs and do not duplicate them.
- `docs/roadmap.md` is the place to record phase progress and open owner decisions.
