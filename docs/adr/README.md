# Architecture decision records

Every change to an invariant, a dependency, the process model or the policy schema gets an ADR (use the `/new-adr` skill) and a matching update to `docs/architecture.md`.
All records are **Proposed** until the owner accepts them. When an ADR is superseded, its status changes and the new ADR links back to it.

Template: Context (optional), Decision, Rationale, Alternatives considered, Consequences (optional), Status, Date, Amends / Amended by.

| ADR | Title | Status | Relations |
| --- | --- | --- | --- |
| [D-001](D-001-meta-agentic-scrum-is-the-organizing-model.md) | Meta-Agentic Scrum is the organizing model, bounded by a grammar | Proposed | amended by D-028 |
| [D-002](D-002-langgraph-1-2-x-is-the-only-orchestrator.md) | LangGraph 1.2.x is the only orchestrator | Proposed |  |
| [D-003](D-003-sprint-topologies-are-persisted-data-compiled.md) | Sprint topologies are persisted data compiled deterministically, with an interpreter fallback | Proposed |  |
| [D-004](D-004-closed-topology-grammar-templates-slots-knobs.md) | Closed topology grammar: templates + slots + knobs, checked by validator rules T1–T10 | Proposed | amended by D-028 |
| [D-005](D-005-two-processes-a-thin-streamlit-ui-and-an-engine.md) | Two processes: a thin Streamlit UI and an engine worker over SQLite WAL | Proposed |  |
| [D-006](D-006-engine-runs-on-windows-toolchains-run-in-pinned.md) | Engine runs on Windows; toolchains run in pinned WSL Docker images through one persistent WSL agent | Proposed |  |
| [D-007](D-007-the-verification-ladder-is-the-judge-definition.md) | The verification ladder is the judge; Definition of Done is set per story kind and target | Proposed |  |
| [D-008](D-008-the-contract-registry-is-the-single-source-of.md) | The contract registry is the single source of truth; interface files are generated | Proposed |  |
| [D-009](D-009-frozen-tests-and-contracts-tamper-and-minimality.md) | Frozen tests and contracts; tamper and minimality gates | Proposed |  |
| [D-010](D-010-sandbox-execution-policy.md) | Sandbox execution policy | Proposed |  |
| [D-011](D-011-code-travels-in-text-envelopes-json-only-for.md) | Code travels in text envelopes; JSON only for small structured artifacts | Proposed | amended by D-029 |
| [D-012](D-012-own-thin-modelgateway-over-the-official-openai-3.md) | Own thin ModelGateway over the official openai 3.x and anthropic 1.x SDKs; no LiteLLM | Proposed | amended by D-029 |
| [D-013](D-013-one-resident-local-moe-model-chosen-by-a-phase-0.md) | One resident local MoE model chosen by a Phase 0 bake-off; explicit profiles | Proposed |  |
| [D-014](D-014-cloud-claude-usage-rules.md) | Cloud (Claude) usage rules | Proposed | amended by D-029, D-030 |
| [D-015](D-015-escalation-ladder-stall-detection-and-stopreason.md) | Escalation ladder, stall detection and StopReason | Proposed | amended by D-030 |
| [D-016](D-016-knowledge-exact-facts-and-fts5-first-qdrant.md) | Knowledge: exact facts and FTS5 first; Qdrant hybrid only after the retrieval eval | Proposed |  |
| [D-017](D-017-lessons-are-evidence-gated-memory.md) | Lessons are evidence-gated memory | Proposed |  |
| [D-018](D-018-policy-versioning-in-run-overlay-offline-policy.md) | Policy versioning, in-run overlay, offline Policy Lab, non-patchable invariants | Proposed |  |
| [D-019](D-019-edit-mode-design.md) | Edit mode design | Proposed |  |
| [D-020](D-020-workspace-format-each-project-is-its-own-git.md) | Workspace format: each project is its own git repository | Proposed |  |
| [D-021](D-021-mvp-scope-nasm-and-gas-on-x86-64-linux-elf64.md) | MVP scope: NASM and GAS on x86-64 Linux ELF64 SysV | Proposed |  |
| [D-022](D-022-language-policy.md) | Language policy | Proposed |  |
| [D-023](D-023-environment-conda-for-the-interpreter-only-pip.md) | Environment: conda for the interpreter only; pip installs from hash-locked files; PowerShell scripts | Proposed | amended by D-031 |
| [D-024](D-024-observability-own-event-log-jsonl-mirror-and.md) | Observability: own event log, JSONL mirror and replay; OpenTelemetry optional | Proposed |  |
| [D-025](D-025-dropped-or-deferred-patterns-from-the-gemini.md) | Dropped or deferred patterns from the Gemini draft | Proposed |  |
| [D-026](D-026-development-time-claude-code-configuration-is.md) | Development-time Claude Code configuration is separate from the product runtime | Proposed | amended by D-032, D-033 |
| [D-027](D-027-documentation-corpus-handling.md) | Documentation corpus handling | Proposed |  |
| [D-028](D-028-ai-composed-sprint-graphs.md) | AI-composed sprint graphs: composition levels, multi-unit loop budgets, mid-sprint re-planning | Proposed | amends D-001, D-004 |
| [D-029](D-029-multi-provider-model-catalog.md) | Multi-provider model catalog (Anthropic, OpenAI, Google Gemini, DeepSeek) in config/models.yaml | Proposed | amends D-011, D-012, D-014; amended by D-038 |
| [D-030](D-030-provider-resilience-and-optional-budgets.md) | Provider resilience and optional budgets | Proposed | amends D-014, D-015 |
| [D-031](D-031-dependencies-in-pyproject-locked-per-platform.md) | Dependencies are declared in pyproject.toml and hash-locked per platform | Proposed | amends D-023 |
| [D-032](D-032-shared-agent-instructions-and-codex-mirror.md) | Shared agent instructions (AGENTS.md), a generated Codex mirror, and the `.reference/` policy | Proposed | amends D-026; amended by D-033 |
| [D-033](D-033-dev-process-conventions.md) | Development-process conventions for coding agents (adapted from the owner's conduit project) | Proposed | amends D-026, D-032; amended by D-035, D-037, D-042 |
| [D-034](D-034-project-owned-qdrant-in-docker-compose.md) | Barthelona runs its own Qdrant from docker/qdrant/compose.yaml | Proposed |  |
| [D-035](D-035-agents-commit-push-and-merge-without-approval.md) | Coding agents commit, push and merge their own PRs without owner approval | Proposed | amends D-033 |
| [D-036](D-036-opt-in-local-training-data-collection.md) | Opt-in, local collection of training data from code-producing attempts | Proposed |  |
| [D-037](D-037-issues-for-findings-and-phase-reviews.md) | Every finding becomes a GitHub issue; each phase ends with a full review | Proposed | amends D-033 |
| [D-038](D-038-qwen3-cloud-provider-via-qwencloud.md) | Add Qwen3 as a cloud provider via Alibaba QwenCloud | Proposed | amends D-029 |
| [D-039](D-039-caching-strategy-prefix-caching-not-semantic-response-cache.md) | Caching strategy: provider prefix caching adopted; semantic response caching rejected | Proposed | amends D-016 |
| [D-040](D-040-compile-down-asm-generation-strategy.md) | Compile-down strategy: compile C/Rust to assembly as an alternative `implement_symbol` path | Proposed | |
| [D-041](D-041-wsl-agent-docker-inspect-allowlist.md) | Add `docker inspect` to the WSL agent allowlist (single target, bart-tc / bart-run* only) | Proposed | amends D-006, D-010 |
| [D-042](D-042-adequacy-and-verifier-check.md) | Adequacy and verifier check for dev threads and the product pipeline | Proposed | amends D-033 |
