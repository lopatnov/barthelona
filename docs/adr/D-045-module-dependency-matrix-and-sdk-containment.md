# D-045: Module dependency matrix and SDK containment

- Status: Proposed
- Date: 2026-10-17
- Amends: D-002, D-005

## Context

Invariant 8 and `docs/architecture.md` §3 give a ring order, but not which sibling packages may import each other, so the promised "import-linter test" cannot be written. `import-linter` is not a dependency, and roadmap F-1 (a stdlib alternative) has no test yet (issue #65). The import graph today is clean and acyclic (cli imports everything it needs; verification imports domain, executors and toolchains; toolchains imports domain and executors; persistence and training import domain only), so this is the cheapest moment to write the rules down.

Separately, D-002 makes LangGraph the only orchestrator, and D-003 keeps an interpreter fallback in case compiled subgraphs cannot resume. The fallback is only cheap if node logic does not depend on LangGraph.

## Decision

1. **Allowed imports** (a package may import only what its row lists, plus the standard library and its own sub-modules):

   | Package | May import |
   | --- | --- |
   | `domain` | nothing from barthelona (Pydantic and stdlib only) |
   | `persistence`, `executors`, `training`, `contracts`, `knowledge`, `memory`, `policy`, `llm` | `domain` |
   | `toolchains` | `domain`, `executors` |
   | `verification` | `domain`, `executors`, `toolchains`, `contracts` |
   | `workspace` | `domain`, `contracts` |
   | `prompting` | `domain`, `knowledge`, `contracts`, `memory` |
   | `nodes` | all of the above, never `engine`, `ui`, `cli` |
   | `engine` | all of the above plus `nodes` |
   | `ui` | `domain`, `persistence`, `config` |
   | `cli` | everything except `ui` |

   `config` in the `ui` row is the settings module that reads the process environment; the model catalog (`config/models.yaml`) is a data file loaded by `llm` from a path or text it is given. The emulator child package gets a row (`domain` only) when it is created.
   Nothing imports `ui`, `cli` or (except `cli`) `engine`.
2. **Ports are defined by the consumer, adapters are injected.** `llm` defines a `CallSink` protocol for recording calls; `persistence` provides the adapter and `engine` wires them. There is one composition root (`engine/wiring.py`, and `cli` for headless tools). No package outside it constructs another's adapter.
3. **SDK containment.** `langgraph` is imported only in `engine`; `streamlit` only in `ui`; `openai`, `anthropic`, `google.genai` only in `llm`; `unicorn` and `capstone` only in the emulator child package. Node logic is a plain async function `(ctx, state) -> update`; `engine` adapts it to LangGraph.
4. **Enforcement.** A stdlib `ast` test (`tests/unit/test_layering.py`) holds the table as data. A new edge is an edit to that table in a reviewed PR. This replaces F-1; no new dependency.

## Rationale

The rows are the edges that exist or are obviously needed, so no existing code is violated. Keeping nodes free of LangGraph makes the interpreter fallback a one-module change and lets graph tests call nodes directly with `FakeGateway` and `FakeExecutor`. Containing the provider SDKs and the GPL emulator library (roadmap F-6) to single packages turns licence and supply-chain questions into questions about one directory.

## Alternatives considered

- **import-linter.** Fine tool, but one more locked dependency for a table of about fifteen rows (D-031: unused or avoidable dependencies are defects).
- **Rings only, no sibling table.** Cannot be tested; siblings drift into a ball of mud (`llm` importing `persistence`, `verification` importing `workspace`).
- **Allow LangGraph in `nodes`.** Simpler to write the first nodes, expensive to leave later.

## Consequences

- `docs/architecture.md` §3 gets the table; `.claude/rules/python.md` is corrected when the test lands.
- If a row turns out wrong, the fix is an ADR amendment, not a silent edit of the test.
