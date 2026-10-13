# D-001: Meta-Agentic Scrum is the organizing model, bounded by a grammar

- Status: Proposed
- Amended by: D-028
- Date: 2026-10-13

## Decision

Keep Scrum as the control model:
- ceremonies are engine phases with typed, persisted artifacts;
- the backlog, sprints, increments, Definition of Done (DoD), review and retrospective are visible in the UI.

"Meta-agency" means:
- a planner composes each sprint's topology from a versioned catalogue of templates, insertion slots and bounded knobs;
- the retrospective changes future sprint assembly through bounded overlays (in-run) and policy patches (offline, via the Policy Lab, activated by a human).

## Rationale

The user explicitly wants the Gemini concept of per-sprint subgraphs plus a retro that rewrites the Sprint Assembly Policy.

Research shows that free-form LLM topologies and in-run self-modification are unreproducible and invite gaming the gates:
- AFlow/ADAS-style search works only against a benchmark;
- multi-agent failures come mostly from system design (MAST).

A grammar plus a validator keeps the concept while every dynamic part stays bounded, validated and reversible.

## Alternatives considered

- Free-form LLM-generated graphs (draft): rejected, not provably terminating or verifiable.
- Scrum as vocabulary only, with a router over fixed templates (verification-first, pragmatist): rejected as the end state because it drops the user's core idea. It is kept as the MVP mode: a rule-based planner over the same catalogue.
