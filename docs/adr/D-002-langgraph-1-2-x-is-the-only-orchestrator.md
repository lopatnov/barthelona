# D-002: LangGraph 1.2.x is the only orchestrator

- Status: Proposed
- Date: 2026-10-13

## Decision

Use langgraph>=1.2.15,<1.3 with these features:
- async nodes;
- AsyncSqliteSaver (langgraph-checkpoint-sqlite 3.1.x) with durability="sync";
- interrupt()/Command(resume) for gates;
- Send for fan-out;
- per-node timeout and RetryPolicy;
- stream version="v2";
- RunControl.request_drain() for cancel.

No second orchestrator. The Claude Agent SDK is not used as an orchestrator.

## Rationale

LangGraph is the only candidate with all of these built in:
- graphs built at runtime;
- a durable SQLite checkpointer;
- human-in-the-loop interrupts;
- fan-out;
- per-node timeouts (1.2).

It is model-agnostic, MIT-licensed, and has been stable since 1.0.

PyPI shows 1.2.15 as of 2026-10-12.

## Alternatives considered

- Pydantic AI graph: no built-in state snapshots.
- CrewAI Flows: fixed decorator topology; Python <3.14.
- MS Agent Framework: Azure-centric; pickle checkpoints.
- OpenAI Agents SDK: 0.x; tracing defaults to OpenAI.
- Burr: small community.
- Plain asyncio: months of rework.
