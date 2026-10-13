# D-005: Two processes: a thin Streamlit UI and an engine worker over SQLite WAL

- Status: Proposed
- Date: 2026-10-13

## Decision

Streamlit 1.65 is a thin client. It writes only:
- runs
- commands
- gate decisions

It reads events via @st.fragment(run_every=1).

The engine worker is a separate single-instance asyncio process that owns LangGraph and everything else.

scripts/run.ps1 starts both. The CLI drives the same worker headless.

## Rationale

Streamlit threads cannot touch st.* and must not outlive their script run. Reruns and browser refreshes must not kill runs. SQLite WAL handles one writer and many readers well. A headless worker makes the engine testable by pytest and by Claude Code.

## Alternatives considered

- Engine threads inside Streamlit: unsupported and fragile.
- FastAPI plus a queue such as Redis: unnecessary infrastructure for a single-user laptop.
