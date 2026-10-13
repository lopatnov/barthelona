# D-014: Cloud (Claude) usage rules

- Status: Proposed
- Date: 2026-10-13
- Amended by: D-029, D-030

## Decision

Cloud use is opt-in per run, with a dollar cap (default $2). Amended by D-030: the dollar cap is optional (default: none, spending always metered), and other providers are added by D-029.

Models (role assignments superseded by D-029 and `config/models.yaml`: Sonnet 5.5 serves main/worker in the `cloud` profile; escalation is flagship-first, starting with Opus 5.5):
- claude-sonnet-5-5 ($2/$10 per million tokens): escalation coder;
- claude-opus-5-5 ($4/$20): planner, architect and hard escalations.

API rules:
- Always set output_config.effort explicitly; Opus 5.5 defaults to medium and its thinking cannot be disabled.
- Never force tool_choice; it returns 400 on Opus 5.5, Sonnet 5.5 and Fable 5.1.
- Use messages.parse() or output_config.format, plus strict tools.
- Strip sampling parameters on Opus 5.5, where they return 400.
- Handle stop_reason "refusal" (with its stop_details category). Superseded by D-029/D-030: send server-side `fallbacks: "default"` on Opus/Sonnet 5.5, then move to the next model in the role chain (another provider), and notify the user at G5 only when the chain is exhausted.
- Put cache_control after the stable prefix.
- Use the Batch API (50% off) for benchmark and Lab runs.

## Rationale

Hybrid gives the best quality per dollar while code stays local by default.

These rules were verified against the current models documentation (cached 2026-10-06).

Assembly work may trip the cyber classifier.

## Alternatives considered

- Cloud-first: privacy and cost.
- Local-only: likely lower solve rate. Remains available as a profile.
