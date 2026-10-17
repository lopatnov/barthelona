# D-042: Adequacy and verifier check for dev threads and the product pipeline

- Status: Proposed
- Date: 2026-10-16
- Amends: D-033

## Context

PR #26 ("Qwen cloud model") nearly merged the wrong `base_url` for the Qwen provider
(`dashscope-intl.aliyuncs.com` instead of the correct endpoint per the Qwen docs). The root
cause was that the rule in `.claude/rules/llm-gateway.md` did not require fetching the
provider's official docs page before writing a URL into `config/models.yaml`.

More broadly, Aleksandr raised the need to verify results in two dimensions:

1. **Adequacy** — did the agent actually do what was asked? (task completion)
2. **Safety** — does the output contain wrong or dangerous artefacts such as wrong API
   endpoints, hallucinated URLs, or fabricated model ids?

This applies to both:
- **Dev threads** (Claude Code or Codex sessions working on this repo).
- **Barthelona's own product pipeline** (the coder/fixer/reviewer roles in §5 and §16).

## Decision

### 1. Dev-thread process (immediate, D-042a)

- `.claude/rules/llm-gateway.md` is strengthened: before writing any `base_url`, model id, or
  price into `config/models.yaml`, the agent must fetch the provider's official docs page (listed
  in the "Provider API docs" row of AGENTS.md) via `docs-researcher` and copy the value
  verbatim. Memory, secondary sources, and previous config files are not sufficient.
- AGENTS.md "Sources of truth" table now lists the six official provider doc URLs
  (Qwen, Anthropic, DeepSeek, OpenAI, Gemini, Qdrant) as a canonical row, so any session can
  find them without searching.

### 2. Product pipeline: config-fact guard (Phase 1, D-042b)

When the gateway loads a provider entry from `config/models.yaml`, it validates the `base_url`
against a compiled allow-list of known hostnames per provider. An unknown hostname is a startup
error, not a runtime error. The allow-list lives in `config/provider_hosts.yaml` and is updated
only with an ADR amendment.

### 3. Product pipeline: cheap adequacy check (Phase 2, D-042c, gated by bench)

After the main coder produces a patch and before the V1–V6 ladder, a lightweight classifier
checks whether the patch touches the files and symbols declared in the task scope. This catches
patches that are syntactically valid but semantically unrelated to the task — a coarse sanity
filter that saves expensive oracle time.

Candidate implementation: TypeSafe **Jev** (a non-generative decision model; picks from supplied
options; claimed ~$0.042/M input tokens and 40–200× faster than frontier LLMs at launch,
2026-10). Jev has no text output and therefore no schema violations, but it can still pick the
wrong option; TypeSafe's own figures suggest disagreement ~1 in 3 on their test tasks. Independent
benchmarks are not yet available.

Per architecture §2.10 ("Measure before adding"), this node is **disabled by default** and
enabled only after the hidden test benchmark shows a gain (fewer wasted oracle runs without
dropping accepted work). It is gated by the same flag as L2 composition.

### 4. Architecture pattern map update (Phase 2, D-042d)

Architecture §5.3 pattern map and §13 will be updated to include:
- **Config-fact guard** as a deterministic startup check (§16.1 or §16.2).
- **Scope guard** node type: classifies whether a patch is in scope for the task before the
  verification ladder.

## Rationale

- Wrong endpoints cause silent, hard-to-debug failures in production (proved by PR #26).
- Fetching the official docs before writing is cheap (one `docs-researcher` call) compared to
  debugging a misconfigured provider.
- A cheap classifier before the oracle ladder reduces wasted wall time without changing the
  acceptance criterion (the oracle still decides).
- Jev is a promising but unproven option; the benchmark gate prevents premature adoption.

## Alternatives considered

- **No change:** the llm-gateway rule already said "verify on provider's docs" but was vague
  enough to be ignored. Rejected: proved insufficient.
- **Regex guard only:** validating the URL format catches typos but not wrong hostnames.
  Complementary, not a replacement for fetching.
- **Second LLM as reviewer:** a cheap generative model to review every patch before the oracle.
  More expensive than Jev and harder to calibrate. Deferred; could be added alongside Jev.
- **Block all external URLs at startup:** too restrictive; providers update their endpoints.

## Consequences

- One extra rule in `.claude/rules/llm-gateway.md` (no code changes, immediate).
- One new row in `config/provider_hosts.yaml` per provider (Phase 1).
- One new node type `scope_guard` registered in the node registry (Phase 2, gated).
- Architecture §5.3 and §13 updated when the node is added (Phase 2).

## Prior art

- TypeSafe Jev announcement and use in RAG hallucination filtering:
  https://www.analyticsvidhya.com/blog/2026/10/rag-hallucination-filter-using-jev/
  (checked 2026-10-16; vendor launch claims, no independent benchmark)
- SAC3 cross-check consistency for hallucination detection:
  https://arxiv.org/abs/2311.01740
- Reflexion (§15.2 reference): gains require external feedback, not self-correction alone.

## Amends

D-033 (dev-process conventions): adds an explicit fetch requirement for provider config values.
