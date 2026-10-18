# D-052: Hardware-aware model placement from measured endpoint profiles

- Status: Proposed
- Date: 2026-10-18
- Amends: D-047, D-049

## Context

Models on several PCs are the system's main resource (owner, 2026-10-18). D-047 and D-049 give an endpoint pool: `endpoints[]`, a loaded-model check, per-endpoint semaphores and breakers, affinity and least in-flight. They know how busy an endpoint is, not how capable it is. A 7B model on an iGPU and a 30B model on a 24 GB card look the same to the scheduler, and `docs/architecture.md` §9.5's "measured velocity" has no source. Issue #156.

Prior art: LM Studio and Ollama report loaded models and context, not speed, so speed must be measured by barthelona. The Phase 0 bake-off already runs timed calls per model (#152 checks the endpoint first).

## Decision

1. **Capability is measured, not declared.** A calibration run per (endpoint, model) records prompt-processing tok/s, decode tok/s, model load time and the largest context the endpoint accepts. Results go to a gitignored `var/endpoint_profiles.json`, keyed by endpoint and `model_hash`, and are re-measured when the model changes or the ledger shows more than 30% drift. Optional declared hints (`ram_gb`, `vram_gb`, `accelerator`, `os`) are used only until the first measurement.
2. **Routing.** The role chain still fixes quality order. Among endpoints serving the same chain entry, the scheduler picks the lowest estimated completion time: queue wait + prompt tokens / prompt rate + expected output tokens / decode rate + reload penalty, subject to context fit. A failed or open-breaker endpoint is skipped as before.
3. **Planning uses the rates.** Sprint unit size, default `max_wall_s` and the run ETA shown in the UI scale with the chosen endpoint's decode rate, still clamped by the caps (invariant 6). A role never starts on an endpoint whose measured context is below the assembled prompt.
4. **Visibility.** The Toolchains & models page shows one row per endpoint: profile, last measurement, in flight, breaker state.
5. **No model sharding** across PCs (D-049 unchanged).

## Rationale

Completion time is what the owner waits for, and it differs by an order of magnitude between PCs. Measuring needs no vendor API and works for LM Studio, Ollama and cloud alike.

## Alternatives considered

- **Declared specs only.** Wrong the day a driver, quantization or thermal state changes.
- **Pure least-loaded.** Sends work to a slow idle PC while a fast one finishes sooner.

## Consequences

- Roadmap F-82: calibration in the Phase 0/1a bake-off harness, routing in the Phase 1b scheduler.
- `LLMCallRecord` already carries timings; the ledger is the drift source.
- D-047 and D-049 get "amended by D-052" in the ADR index.
