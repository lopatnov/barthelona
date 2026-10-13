# D-028: AI-composed sprint graphs: composition levels, multi-unit loop budgets, mid-sprint re-planning

- Status: Proposed
- Date: 2026-10-13
- Amends: D-001, D-004

## Context

The owner does not want one fixed graph that every task runs through. For each unit of work, the system should form the loop graph it needs from ready-made pieces, choose how a loop is bounded (by outcome, time or count), and reshape the graph when the plan meets reality. D-004 keeps a closed grammar of templates + slots + knobs, with an LLM planner only from Phase 2. That keeps the engine safe but under-delivers on the owner's central requirement.

## Decision

1. **Ready-made pieces stay in code.** Node types (registry) and templates are written and tested by developers. The AI composes; it never invents node types or engine code.
2. **Three composition levels**, set per run by `planner.composition_level`:
   - **L0:** rule-based template choice with default knobs. Always available; it is the fallback.
   - **L1:** an LLM chooses the template, slot insertions, knob values, per-loop budgets and the unit size. Output is constrained to enums and bounded numbers generated from the active policy. Experimental flag in Phase 1; default from Phase 2 if the bench shows no regression versus L0.
   - **L2:** an LLM (strong tier only) composes whole task pipelines from registered node types, edges and loops. Phase 2, behind a flag; enabled per profile only when the bench shows a gain over L1.
3. **One validator for all levels.** Rules T1–T10 (vocabulary, structure, totality, bounded cycles, verification dominance, write scopes, budget, tier/consent, gate hygiene) apply unchanged. Generated pipelines are therefore as safe as templates.
4. **Multi-unit loop bounds.** `LoopBound` gains `max_wall_s`, `max_tokens` and `max_usd` next to `max_iters`; the loop exits at the first bound reached, or on its success edge. Policy caps bound every value.
5. **Mid-sprint re-planning.** A stall or `exit_escalate` hands the remaining work back to the planner. The planner returns a revised topology for the remainder only, which is validated, persisted as `sprints/NN/topology.rK.json`, and compiled. Re-planning is bounded by `max_replans` (default 1, cap 3). Resume uses the latest persisted revision.
6. **Fallbacks.** An invalid proposal gets at most 2 repair attempts with the validator's errors, then L0. A model that keeps failing drops to L0 for the rest of the run.
7. **Visibility.** The UI shows, per sprint, the level used, the graph (DOT) and the planner's rationale.

## Rationale

- It delivers what the owner asked for (an AI-shaped loop per unit of work, plus re-planning) while keeping the guarantees that matter for assembly: termination, verification dominance, frozen tests and budgets.
- Constrained decoding against registry-generated enums makes L1 feasible for small local models. L2 is reserved for tiers that can handle it.
- Persisting every revision before execution keeps crash/resume deterministic (D-003).
- Benchmark gating avoids "self-designing workflows" that look clever but solve fewer tasks (cf. ADAS, https://arxiv.org/abs/2408.08435; AFlow, https://arxiv.org/abs/2410.10762).

## Alternatives considered

- **Free-form LLM-written graphs or code (Gemini draft):** no termination or verification guarantees, and resume is fragile. Rejected.
- **Templates only (D-004 as written):** safe, but the AI cannot adapt the shape of the work. Kept as L0 and as the fallback.
- **Rewriting the policy in-run:** unreproducible. Policy changes stay offline in the Policy Lab (D-018).

## Consequences

- Phase 1 must ship the registry, validator, compiler and topology persistence early, because L1 is built on them.
- The bench needs per-level reporting: L0 vs L1 vs L2, with solve rate, attempts, time and cost.
- Property tests must also fuzz L2-shaped pipelines (random node/edge sets drawn from the registry).
