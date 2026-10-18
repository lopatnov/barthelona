# D-050: Barthelona is an oracle-driven software builder; assembly is the first target family

- Status: Proposed
- Date: 2026-10-18
- Amends: D-021, D-040

## Context

The owner asked (2026-10-17) whether the finished system could build a JSON-configured reverse proxy with a load balancer, a game from a 2D snake up to a 3D racing game, and a task-scheduler app, and whether the architecture fits those ambitions. The answer in the plan review (issue #105) was no: the architecture fits verified assembly modules. On 2026-10-18 the owner said to decide in favour of the best results for applications, including very good-looking ones, and to keep the work moving without waiting.

What carries over unchanged: bounded loops with `StopReason`, the ladder as registered checks per target family (D-046), contracts as the single source of truth, frozen tests and the tamper gate, gates, the event log and provider chains. What is assembly-specific: dialect adapters, V3/V4 ABI checks, rule cards and the no-network sandbox profile.

Prior art:
- SWE-agent (NeurIPS 2024): a purpose-built interface with guardrails, not graph design, drove results; a new family is mostly a new interface and checks ([paper](https://papers.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html)).
- Agentless (arXiv 2407.01489): localize, repair, validate with tests beat agent frameworks at low cost, so each family's check set matters more than orchestration ([abstract](https://arxiv.org/abs/2407.01489v2)).
- Aider: edit format changes results for weaker models ([unified diffs](https://aider.chat/docs/unified-diffs.html)); applies to every family.
- Visual feedback for UI generation: not researched yet; `docs-researcher` before the web family opens (F-72).

## Decision

1. **Product aim.** Barthelona creates and edits software projects whose correctness is decided by oracles, not by model opinion. Assembly stays the first and the proving target family. A **target family** (D-046) is the extension unit: its adapters, its registered checks, its sandbox profile, rule cards and bench tasks.
2. **Order, focus rule intact.** Phase 0 and the Phase 1a walking skeleton finish on the assembler first. The second family starts when Phase 1b's exit criteria are met, in parallel with Phase 2 (a new Phase 6 in the roadmap).
3. **Second family: C applications** on Linux (gcc/clang). Oracles: build with warnings as errors, sanitizers (ASan/UBSan), unit and golden-I/O tests, and a sandbox profile with **loopback-only networking** so servers can be tested (reverse proxy and balancer, task schedulers, CLIs), plus a fake clock for time-dependent tests. C is already the compile-down input (D-040) and gcc is in `bart-tc`.
4. **Third family: web and 2D** (HTML/JS/CSS with Node tests, a headless browser, and 2D games as deterministic simulations). Oracles judge logic and structure: unit tests, replayable input scripts, lint, accessibility checks, layout and contrast rules. **Beauty is not machine-decidable.** For looks, the loop adds screenshots at set viewport sizes for a vision-capable model to critique (advisory, invariant 1 holds) and a human gate (G4) decides. 3D at the level of a commercial racing game stays out of range; it needs assets and engines no oracle can judge.
5. **Invariants unchanged.** Oracles decide, generated code runs only in the sandbox, `contracts.yaml` and tests are frozen while coding, bounded loops, secrets from env. Each family declares its own contract kinds (symbols and ABI for assembly; module APIs and HTTP routes for C and web) under the same registry rules.
6. **Larger projects.** A proxy or scheduler is hundreds of functions. The context assembler and repo map (§14, §15.3) are tested against a project of that size before the second family ships; edit mode (Phase 3) is not delayed.
7. **No new family without** a `new-adr` for its oracle set, a conformance kit and at least 5 bench tasks within budget (Phase 4 rule).

## Rationale

The expensive, reusable part of the system is the oracle-and-gate machinery, which does not care what the target is. Most applications the owner has in mind (servers, tools, small games) can be judged by tests, which a language runtime provides. Starting with C keeps the sandbox model close to the existing one and reuses the compile-down work. Taking the assembler to a working end-to-end result first stays consistent with the focus rule and gives the measured baseline that every later family is compared with.

## Alternatives considered

- **Stay assembler-only (option A in #105).** Matches the original aim, but leaves the owner's stated ambitions out of reach by design.
- **Go general immediately.** Violates the focus rule and spreads the first measurement thin.
- **Skip C, go straight to web.** Web needs a browser sandbox and visual judging, which are harder than C's tests.

## Consequences

- Roadmap: new Phase 6 (C family, then web and 2D); F-34, F-35, F-36 rows updated; issues #60, #61 and #105 answered by this decision.
- `AGENTS.md`, the README and `docs/architecture.md` §1 describe an assembler-only product; the architecture §1 gets a pointer now, `AGENTS.md` and README wording follow in a gated change after the guardian review (F-71).
- The `contracts.yaml` schema and `Dialect`/`TargetProfile` enums gain a `family` axis when family two starts; no change before then.
- Visual-feedback research (F-72) happens before the web family opens, not now.
