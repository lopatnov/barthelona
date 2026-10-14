---
name: new-adr
description: Create a new architecture decision record in docs/adr with the next free D-number, update the ADR index and the affected sections of docs/architecture.md.
disable-model-invocation: true
argument-hint: "<title>"
---
# New ADR: $ARGUMENTS

Existing ADRs:
!`ls docs/adr`

1. Take the next free number after the highest `D-NNN` above. Slug: lowercase title words joined by `-`, at most about 48 characters, cut at a word boundary.
2. Create `docs/adr/D-NNN-<slug>.md`:
   ```markdown
   # D-NNN: <Title>

   - Status: Proposed
   - Date: <today, YYYY-MM-DD>
   - Amends: <D-xxx, if any>        (omit the line if none)

   ## Context
   ## Decision
   ## Rationale
   ## Alternatives considered
   ## Consequences
   ```
   Cite URLs for any version-, price- or date-sensitive fact.
3. If it amends or supersedes earlier ADRs, add `- Amended by: D-NNN` (or change `Status:` to `Superseded by D-NNN`) in those files.
4. Add a row to `docs/adr/README.md`.
5. Update the affected sections of `docs/architecture.md` (and `AGENTS.md` if an invariant changed) in the same change.
6. Show the user the new ADR and the diff summary. Commit it on the working branch after the review gate (AGENTS.md is a gated path); the ADR stays Proposed until the owner accepts it.
