# D-024: Observability: own event log, JSONL mirror and replay; OpenTelemetry optional

- Status: Proposed
- Date: 2026-10-13

## Decision

Recorded in SQLite (with a var/runs/<id>/events.jsonl mirror):
- RunEvent and LLMCallRecord
- execution logs
- metrics

The UI reads them.

`barthelona replay` uses LLM cassettes.

With BARTHELONA_OTEL=1, traces go via openinference-instrumentation-langchain to Arize Phoenix, which runs separately (Elastic-2.0 license).

## Rationale

The event log is needed anyway for the UI and gives full reproducibility.

Phoenix is optional and heavy.

## Alternatives considered

- Self-hosted Langfuse: needs Postgres, ClickHouse, Redis and S3; too heavy.
- LangSmith: SaaS, or an enterprise licence to self-host.
