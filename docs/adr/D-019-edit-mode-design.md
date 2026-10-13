# D-019: Edit mode design

- Status: Proposed
- Date: 2026-10-13

## Decision

Steps:
1. Import into a workspace clone on branch bart/<run>.
2. Detect dialect and target, and the user confirms.
3. Baseline build; if it fails, the first story is fix_build.
4. Build a repo map with regex extractors and Personalized PageRank.
5. Recover inferred contracts via nm + Capstone.
6. Freeze characterization tests.
7. Write a ChangeSpec with superseded tests; G1.
8. Localize: deterministic shortlist, then the LLM picks from an enum.
9. Apply symbol or hunk patches under the minimality gate and run full regression.

Contract deltas go through contract_change and G2.

## Rationale

The draft covered only creation, and the user needs editing.

Characterization tests are the oracle for not breaking behaviour. Minimal diffs and branch isolation make changes reviewable and reversible.

## Alternatives considered

- Regenerate whole files: breaks unrelated code.
- Vector RAG over project code: a repo map is enough for small projects.
