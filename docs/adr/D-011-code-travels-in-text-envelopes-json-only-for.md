# D-011: Code travels in text envelopes; JSON only for small structured artifacts

- Status: Proposed
- Amended by: D-029
- Date: 2026-10-13

## Decision

Code formats:
- Whole files: `=== FILE: path ===` … `=== END ===`.
- Edits: SEARCH/REPLACE blocks, where each SEARCH must match exactly once, or SYMBOL blocks.

The strict parser enforces path fences and counts a parse failure as a repair attempt.

JSON with a schema (grammar-constrained locally; in the cloud each provider's mechanism, see D-029 and architecture §16.3: DeepSeek supports only json_object, so its output is always validated and repaired) is used for the spec, contracts, plans, verdicts and localization.

## Rationale

Small local models mangle the escaped backslashes and quotes that assembly needs inside JSON strings.

Constrained decoding guarantees JSON that parses, not correctness, so Pydantic and semantic validation still follow.

## Alternatives considered

- Everything in JSON: high failure rate locally.
- Tool-calling loops for edits: weak and inconsistent on local models in LM Studio; deferred to cloud tiers.
