# D-030: Provider resilience and optional budgets

- Status: Proposed
- Date: 2026-10-13
- Amends: D-014, D-015 (supersedes D-014's refusal-to-local rule: refusals use server-side fallbacks, then the next model in the chain)

## Context

The owner wants to be able to enter a budget for paid cloud models in the UI. The budget is optional. The system must expect that money can run out and that cloud models are not always reliable. D-014 made a $2 per-run cap the default and treated cloud failure mostly as an escalation detail.

## Decision

1. **Budgets are optional.**
   - `budget.run_usd`, `budget.monthly_usd` and `budget.per_provider_usd` default to `null` (no cap).
   - Spending is always metered per call, sprint, run and provider, and shown in the UI.
   - When a cap is set, the gateway enforces it with **reserve-then-settle**: reserve the worst-case cost before the call, refuse the call if the reservation does not fit, then settle the actual cost from reported usage.
   - At `warn_at` (default 80%) the UI warns. At 100% the `on_exhausted` policy applies: `ask` (G5, default), `fallback_local`, or `stop`.
2. **Errors are classified as Transient, Terminal-for-provider, Model-level or Output-level** (`docs/architecture.md` §16.6, with the verified provider codes). Running out of credit or hitting a spend limit is **terminal for that provider**, not a budget stop of the run.
3. **Circuit breakers** are kept per provider and per model:
   - transient: opens after 3 failures in 120 s, half-opens after 60 s;
   - terminal: half-opens after 30 min with one probe.

   State is persisted and shown in the UI.
4. **Retries** apply only to transient errors: exponential backoff with full jitter, `Retry-After` as the minimum wait, at most 3 attempts. SDK-internal retries are disabled (`max_retries=0`) so attempts are not multiplied.
5. **Fallback chains always end in the local model.** On fallback to a weaker tier, the planner shrinks the unit of work (D-028).
6. **If no model is reachable at all**, the run drains to a resumable checkpoint with the new `StopReason.no_model_available`.
7. **Every fallback is visible** as an event (provider, error class, next model), and every `LLMCallRecord` stores which model actually served the role.

## Rationale

- The owner's explicit requirement: money can run out and cloud models are not always reliable.
- Treating credit exhaustion as a provider failure keeps runs going on other providers or locally instead of stopping.
- Reserve-then-settle is the only way a cap can be a hard guarantee when output length is unknown in advance.
- Oracles decide acceptance (D-007), so degraded models can waste attempts but cannot corrupt projects.

## Alternatives considered

- **A mandatory default cap** (D-014's $2): rejected as the default; the owner wants the cap optional. It remains available per run.
- **Relying on SDK retries only:** they do not distinguish an empty balance from a rate limit, and they do not fail over between providers.
- **Stopping the run when a provider fails:** wastes completed work and contradicts local-first.

## Consequences

- Error-mapping tables per backend need fixtures captured from real error bodies, refreshed when providers change their APIs.
- Graph tests must cover: provider failover mid-sprint, terminal circuit then recovery, cap reached (with ask, fallback_local and stop), and no model available, then resume.
