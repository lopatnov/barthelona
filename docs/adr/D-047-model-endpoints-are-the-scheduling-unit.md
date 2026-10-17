# D-047: Model endpoints are the scheduling unit of the catalog

- Status: Proposed
- Date: 2026-10-17
- Amends: D-029

## Context

`config/models.yaml` has one `lan_lmstudio` provider with one `base_url`, so running models on several PCs (issue #44) is impossible without changing the catalog schema. The Phase 1 catalog loader will freeze that schema, so the shape has to be decided before the loader is written. Different PCs hold different models at different context sizes, so a provider-level setting cannot describe availability.

## Decision

1. A provider has `endpoints[]`, each with `base_url`, `host_label`, `max_concurrency`. A provider with a single `base_url` is the one-endpoint case, so the current file stays valid.
2. A model is usable on an endpoint only if that endpoint reports it loaded (LM Studio `/api/v1/models`, Ollama `/api/ps`); the health probe (§16.6) records this per endpoint.
3. The gateway's scheduler picks an (endpoint, model) pair: affinity first (avoid reloads), then least in-flight. Semaphores and circuit breakers are kept per endpoint.
4. `LLMCallRecord` gets `endpoint`. Shared Qdrant stays a separate `QDRANT_URL`.
5. Remote toolchain hosts are out of scope; they would be a new executor transport (D-043).

## Rationale

The endpoint is where concurrency, health and loaded models actually live. Modelling it now costs one list in the loader; retrofitting it after the gateway exists touches the router, breakers, ledger and UI.

## Alternatives considered

- **Pool as a provider-level list with one model set.** Wrong when the PCs differ.
- **One provider entry per PC.** Works today, but the role chains would list every PC by hand and cannot balance.

## Consequences

- Implemented with the Phase 1 loader (roadmap F-13, issue #44 for the scheduling part). `docs/architecture.md` §16.1 and §16.2 are updated in the same change.
