# Barthelona Architecture

Version 1.0 · 2026-10-13 · Status: proposed baseline, pending owner review (see `docs/roadmap.md` § Open decisions).

Decisions are recorded as ADRs in `docs/adr/` (index: `docs/adr/README.md`). This document supersedes the Gemini brainstorming draft, which is kept only in `docs/archive/` and is non-authoritative: its model names and statistics are partly fabricated or outdated.

How this document was produced: five web-verified research reports (Gemini-draft audit, orchestration stack, assembler toolchains, knowledge layer, Claude Code configuration), three competing architecture proposals (Scrum-faithful, verification-first, local-first pragmatist), and a judged synthesis that starts from the verification-first spine and keeps Meta-Agentic Scrum as the organizing model. Owner requirements added after the synthesis are folded in: AI-composed sprint graphs (§9.5), four cloud providers (§16.2), optional budgets and provider resilience (§16.6), and a pattern map (§5.3).

Two terms are used throughout:

- **Product**: the barthelona runtime described here.
- **Claude Code**: the developer assistant used to build the product. Its configuration (`CLAUDE.md`, `.claude/`) is never shipped with the product or loaded by it.

## 1. Purpose and scope

Barthelona is a local-first agentic system. In a Streamlit UI the user:

1. Selects an assembler **dialect**. MVP: NASM, GAS Intel syntax, GAS AT&T syntax. Later: FASM, fasmg/fasm2, YASM, the MASM-compatible asmc and UASM, and ml64.
2. Selects a **target preset**: architecture, OS, ABI, object format and link mode.
3. Chooses **create** (new project) or **edit** (existing project).
4. Describes, in English, Russian or Ukrainian, what to build or change.

The system runs a **Meta-Agentic Scrum** process:

1. It turns the request into an approved spec, interface contracts and tests.
2. It implements the work in bounded sprints until a multi-file assembly project builds and passes its tests.

The result is a self-contained git repository that builds without barthelona.

**Direction (D-050).** Assembly is the first and the proving **target family**. Barthelona is an oracle-driven software builder: later families (C applications, then web and 2D) reuse the same loops, gates and ladder with their own adapters, checks and sandbox profiles, and are scheduled in roadmap Phase 6, after the assembler pipeline works end to end. Everything below describes the assembler family unless it says otherwise.

**Machine** (measured):

- Windows 11 Pro; Intel Core Ultra 7 155H with Intel Arc iGPU (no NVIDIA GPU); 32 GB RAM.
- WSL2 Ubuntu 26.04 with Docker.
- LM Studio, OpenAI-compatible, at `http://127.0.0.1:1234/v1`. Ollama is installed but not running by default.
- Optional cloud providers (the owner holds keys for five): Anthropic, OpenAI, Google Gemini, DeepSeek, and Alibaba QwenCloud / Qwen3 (added D-038; preferred for its Slavic-optimised tokenizer). They are interchangeable behind one gateway and configured in `config/models.yaml` (§16.2).
- Qdrant runs in WSL Docker. Barthelona has its own instance (`docker/qdrant/compose.yaml`, `127.0.0.1:6343`, named volume; D-034), separate from the owner's `qdrant-db` on 6333. It is reachable only while the WSL VM is running.

**Out of scope for v1:**

- running generated code outside a sandbox;
- build files written by an LLM;
- multi-agent debate;
- autonomous web research;
- in-run rewriting of prompts or rules;
- fine-tuning (the opt-in training-data collection that would feed it is in scope, §19, D-036);
- KolibriOS (optional, later).

## 2. Principles

1. **Oracles decide; models propose.** "Done" is decided by:
   - the assembler and the linker;
   - the symbol check;
   - static ABI lint;
   - the emulator's ABI checks;
   - sandboxed tests.

   LLM review is advisory: it may add findings or propose tests, but it never accepts code. Self-correction without external feedback is unreliable (https://arxiv.org/abs/2310.01798).

2. **Meta-agency inside a grammar.**
   - Each sprint's workflow topology is data, composed from registered building blocks: a versioned catalogue of templates, insertion slots and bounded knobs (L0/L1), or, behind a flag, whole task pipelines built from registered node types (L2, §9.5).
   - Before anything runs, a deterministic validator proves the topology terminates, is verified and fits its budget.
   - Every graph, whoever composed it, passes validator rules T1–T10 before it runs. Node types are code; an LLM never invents node types or executes engine code it wrote.
3. **One source of truth per concern.**
   - `project.yaml`: target and build.
   - `contracts.yaml`: the register, stack and flag contract of every exported symbol.
   - `tests/`: behaviour.

   Everything else is generated from these and never written by an LLM: headers, stubs, Makefile, C prototypes, emulator mocks.

4. **Frozen while coding.** Approved tests and contracts are read-only for every coding role. Changing them is a separate, gated kind of story.
5. **Fresh, budgeted context.** No chat histories. Every LLM call is assembled from the registry, files and facts, with stable blocks first.
6. **Every loop is bounded, and every stop has a reason** (`StopReason`).
7. **Local-first, cloud as an unreliable accelerator.**
   - One local model stays loaded, and every role's fallback chain ends in it, so the system degrades instead of dying when the internet, a provider or the money is gone.
   - Cloud providers are used only with per-run consent. Spending is always metered; a dollar cap is optional.
   - A provider can fail, throttle or run out of credit at any moment. That is a normal event with a defined reaction (§16.6), never a crash.
8. **Untrusted by default.**
   - Generated binaries run only in hardened containers or the emulator process.
   - Imported repositories, docs and web text are data, never instructions.
9. **Reproducible and reversible.**
   - A branch per run and a commit per green increment.
   - Immutable policy versions and pinned toolchain image digests.
   - Full traces with replay.
10. **Measure before adding.** A benchmark with hidden tests gates every change to prompts, models or policy. It also gates every optional subsystem: vector RAG, lesson injection, critics, candidate sampling.

## 3. System overview

```
Browser -> Streamlit UI (Windows, conda)          Engine worker (Windows, conda, asyncio + LangGraph 1.2)
           pages, forms, polling fragments        |- LLM gateway -> LM Studio 127.0.0.1:1234 | Anthropic/OpenAI/Gemini/DeepSeek (opt-in, §16.2)
              | writes runs/commands/decisions    |- Knowledge: var/kb/facts.sqlite + FTS5 (Qdrant hybrid in P3)
              v reads events/gates                |- Emulator child process (Unicorn + Capstone)
      var/app.sqlite (WAL) <--------------------> |- WSL agent (one long-lived wsl.exe stdio pipe, JSON lines)
      var/checkpoints.sqlite (LangGraph)          |     |- docker exec -> bart-tc  (toolchain container, no network)
                                                  |     '- docker run  -> bart-run (ephemeral sandbox per test batch)
                                                  '- Workspaces: <workspaces>/<slug>/ (one git repo per project)
```

| Process        | Where                                 | Role                                                                                                                      |
| -------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| UI             | Windows, conda env                    | Thin client. Queues runs, answers gates, renders events. Never imports engine or LangGraph code.                          |
| Engine worker  | Windows, conda env                    | Single instance, guarded by `var/worker.lock`. Owns LangGraph, the gateway and the executors. Runs headless from the CLI. |
| WSL agent      | WSL, `python3`, standard library only | Staging (tar in and out), command execution from argument lists only, path fence, timeouts, output caps.                  |
| `bart-tc`      | WSL Docker, long-lived                | nasm, yasm, fasm, binutils, gcc, make, gdb. Versions are pinned by the image digest.                                      |
| `bart-run`     | WSL Docker, one per test batch        | Runs generated binaries and C harnesses under the sandbox profile (§13.4).                                                |
| Emulator child | Windows child process                 | V3 lint and V4 emulation. Killed on timeout.                                                                              |

**Where the engine runs (D-049, amends D-006).** The diagram above shows the owner's Windows PC. The same engine runs unchanged on a Linux host with Docker (Debian or Ubuntu): the executor uses `LocalTransport` and the agent runs as a local process, so there is no `wsl.exe` hop. Linux is the reference host (CI exercises it); Windows with WSL2 stays supported and keeps these reasons: conda is installed there, LM Studio is reachable on the host loopback (`127.0.0.1:1234`) without WSL networking, and ml64 can later run natively as a `windows-native` executor. No package outside `executors`, `scripts/` and the runbook may assume a host OS.

**Model endpoints may live on other PCs (D-049, D-047).** LM Studio or Ollama on any PC (Windows, Debian, macOS) is an endpoint of the catalog; the gateway needs only HTTP reach. More PCs add throughput (independent calls in parallel, roles placed on the endpoint that holds the right model, failover), not one bigger model: sharding a model across PCs is out of scope. Toolchains and generated code stay on the engine host.

All Linux tools run in pinned images, so the product needs no `apt` installs in WSL and its toolchain is reproducible.

Measured costs:

- a warm `wsl.exe` call takes about 150 ms;
- a hardened `docker run` takes 0.5–0.9 s.

So the worker keeps one WSL agent and one toolchain container alive, and runs tests in batches.

**Layering** (D-045), enforced by a stdlib `ast` test (`tests/unit/test_layering.py`) that holds this table as data; a new edge is a reviewed edit of the table:

| Package                                                                                     | May import                                         |
| ------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `domain`                                                                                    | nothing from barthelona (Pydantic and stdlib only) |
| `persistence`, `executors`, `training`, `contracts`, `knowledge`, `memory`, `policy`, `llm` | `domain`                                           |
| `toolchains`                                                                                | `domain`, `executors`                              |
| `verification`                                                                              | `domain`, `executors`, `toolchains`, `contracts`   |
| `workspace`                                                                                 | `domain`, `contracts`                              |
| `prompting`                                                                                 | `domain`, `knowledge`, `contracts`, `memory`       |
| `nodes`                                                                                     | all of the above; never `engine`, `ui`, `cli`      |
| `engine`                                                                                    | all of the above plus `nodes`                      |
| `ui`                                                                                        | `domain`, `persistence`, `config`                  |
| `cli`                                                                                       | everything except `ui`                             |

- Nothing imports `ui`, `cli`, or (except `cli`) `engine`. The engine never imports Streamlit.
- Ports are defined by the consumer and adapters are injected at one composition root (`engine/wiring.py`; `cli` for headless tools). Example: `llm` defines a `CallSink` protocol and `persistence` provides the adapter.
- SDK containment: `langgraph` only in `engine`; `streamlit` only in `ui`; `openai`, `anthropic`, `google.genai` only in `llm`; `unicorn`, `capstone` only in the **emulator child package** (`src/barthelona/emulator/`). A node is a plain async function `(ctx, state) -> update` that `engine` adapts to LangGraph, which keeps the interpreter fallback (§7) a one-module change.

## 4. Domain model (Pydantic v2, `src/barthelona/domain/`)

**General rules:**

- Every top-level document (`barthelona.domain.DOCUMENTS`; `python -m barthelona schema` lists them and prints their JSON schemas) has a `schema_version`; nested value objects take the version of the document that holds them. Every model serializes to JSON or YAML, has fields that cannot be reassigned (nested lists and dicts are not deep-frozen); `model_copy(update=...)` skips validation, so updates from untrusted input go through `model_validate` and rejects unknown keys. Hashes (`spec_hash`, `hash`) cover the canonical JSON without the model's own hash fields.
- The models check field shapes and local consistency only (unique ids, a stopped run has a `StopReason`, sprint layers cover every task once, a sprint topology's tasks map to its pipelines) and absolute ceilings; the LLM-facing decoding schema is generated from the active policy (§9.4) and is tighter. Graph rules for topologies are validator rules T1–T10 (§9.4).
- Every model an LLM fills is flat: no recursion, minimal `$ref`/`anyOf`, enums, and length limits. This lets grammar-constrained decoding work on local models.

**Target and project**

- `TargetProfile`:
  - `preset`, e.g. `linux-x64-nasm-static`;
  - `dialect`: `nasm|gas-intel|gas-att|fasm|fasmg|fasm2|yasm|asmc|uasm|masm-ml64`;
  - `dialect_version`;
  - `arch`: `x86-16|x86|x86-64|aarch64|riscv64`;
  - `os`: `linux|windows|bare|dos`;
  - `abi`: `sysv64|win64|cdecl32|aapcs64|lp64d|none`;
  - `obj_format`: `elf64|elf32|win64|pe64-direct|bin`;
  - `link`: `none|ld|libc|mingw|msvc|lld-link`;
  - `pie`, `entry`;
  - `run_env`: `docker-native|docker-qemu-user|docker-wine|qemu-system|emu-only`;
  - `dod`: map from story kind to ladder level.
- `ProjectSpec` (create mode):
  - `id`, `slug`, `request_original`, `request_lang`, `summary_en`, `target`;
  - `requirements`: list of `Requirement{id, text, test_ids}`;
  - `modules`, `constraints`, `non_goals`, `assumptions`, `approved_at`.
- `ChangeSpec` (edit mode):
  - `intent_en`, `requirements`, `new_test_ids`;
  - `superseded_test_ids`: characterization tests that are expected to change;
  - `expected_contract_deltas`: empty by default;
  - `scope_hints`: files and symbols named in the request.
- `ModuleSpec`: `path`, `purpose`, `exports`, `imports`, `max_lines` (default 250), `owner_story`.

**Contracts** (`contracts.yaml`, the single source of truth)

- `ContractRegistry`:
  - `version` (int), `target`;
  - `symbols`: map of name to `Symbol`;
  - `structs`: map of name to `StructDef{fields[{name, type, off}], size}`;
  - `consts`, `frozen` (list of symbol names), `hash`.
- `Symbol`:
  - `name`; `kind`: `func|data|const|macro|struct`; `module`;
  - `visibility`: `global|local|extern`; `abi`: `target|custom`;
  - `inputs` and `outputs`: lists of `RegisterContract{reg, type, desc}`;
  - `flags_out`, e.g. `{CF: "1 on error"}`;
  - `clobbers`;
  - `stack`: `StackContract{entry_align = "8 mod 16", max_depth, red_zone}`;
  - `mem_effects`: list of `{arg, access: r|w|rw, size_expr}`;
  - `preconditions`, `calls`;
  - `status`: `planned|stub|implemented|tested|inferred`;
  - `test_ids`;
  - `hash`: a change marks dependent modules as stale.

**Backlog and sprints**

- `BacklogItem`:
  - `id`;
  - `kind`: `create_module|implement_symbol|fix_bug|change_behavior|refactor|contract_change|fix_build|integration|spike`;
  - `title`, `narrative`, `requirement_ids`, `acceptance_test_ids`, `modules`, `symbols`, `depends_on`;
  - `size`: `XS|S|M`; `priority`; `tags`;
  - `status`: `proposed|approved|ready|in_sprint|done|blocked|dropped`;
  - `attempts`, `stop_reason`.
- `SprintPlan`: `sprint_no`, `goal`, `item_ids`, `tasks`, `layers` (list of task-id lists), `topology_request`, `budget`.
- `Task`: `id`, `item_id`, `module`, `symbols`, `depends_on`, `write_scope` (globs), `role_hint`.
- `TopologyRequest` (LLM-fillable; enums and bounded numbers only):
  - per task: `{task_id, template_id, insertions{slot: [node_type]}, knobs{name: value}, loop_budgets{"src->dst": {max_iters, max_wall_s, max_tokens, max_usd}}, unit_size: symbol|module|module_group}` (L1);
  - or, at L2, `pipelines{task_id: TaskPipeline}` built from registered node types (a request is either L1 or L2, never both);
  - `rationale`, at most 300 characters.
- `SprintTopology`, `TaskPipeline`, `NodeSpec`, `EdgeSpec`, `LoopBound`: see §9.

**Tests and verification**

- `TestCase`:
  - `id`; `kind`: `emu_call|abi_conformance|c_harness|io_golden|differential|boot`;
  - `symbol`, `level`, `inputs`;
  - `expect`: `ret`, `regs`, `mem`, `stdout`, `exit_code`;
  - `reference`: path to a Python reference model;
  - `generator`: seed, count, value domains;
  - `visibility`: `visible|hidden`;
  - `origin`: `user|spec_agent|test_author|characterization|bench`;
  - `approved`, `locked = true`, `sha256`.
- `Diagnostic`:
  - `tool`; `level`: `V0` to `V8`, or `tamper`, `minimality`, `schema`;
  - `severity`: `fatal|error|warning|note`;
  - `code`, e.g. `A2008`, `LNK2019`, `-w+orphan-labels`, `abi.misaligned_call`;
  - `message`, `file`, `line`, `macro_stack`, `symbol`, `error_sig`, `raw_ref`.
- `LevelResult{level, status: pass|fail|skipped|unsupported, diagnostics, secs}`.
- `VerificationReport{levels, tests_passed, tests_failed, toolchain_versions}`.
- `Increment`: `sprint_no`, `branch`, `git_sha`, `tag`, `stories_done`, `contracts_version`, `frozen_symbols`, `report`, `artifacts` (path → sha256), `image_digest`.

**Code changes** (never inside JSON)

- `Patch` is a list of:
  - `FileWrite{path, content}`;
  - `HunkEdit{path, search, replace}`;
  - `SymbolEdit{path, symbol, new_text}`.
- Patches are parsed from text envelopes (§16.3).

**Memory and policy**

- `Lesson`:
  - `id`; `kind`: `pitfall|recipe|toolchain_quirk|convention`;
  - `rule`: at most 40 words, imperative;
  - `rationale`;
  - `trigger{error_sig, terms}`;
  - `scope{dialect, arch, os, format, toolchain_range}`;
  - `evidence[{run, sprint, error_before, diff_hash, verified_by}]`;
  - `regression_check{asm, cmd, expect}`;
  - `status`: `candidate|active|approved|deprecated|rejected`;
  - `alpha`, `beta`, `uses`, `created`, `last_confirmed`;
  - `source`: `retro|human|web`; `url`.
- `PolicyVersion`: `id`, `parent`, `templates`, `prompts`, `rules`, `knobs` (ranges and defaults), `caps`, `released`, `sha256`.
- `OverlayChange`: `project`, `knob`, `old`, `new`, `reason`, `sprint`.
- `PolicyPatch`:
  - `id`, `base_version`;
  - `kind`: `prompt|rule|template|knob_default`;
  - `ops` (JSON Patch), `rationale`, `evidence_runs`, `lab_result`;
  - `status`: `proposed|lab_passed|lab_failed|approved|active|rolled_back|rejected`.

**Runs and events**

- `Run`:
  - `id`, `mode`, `workspace`, `target`;
  - `profile`: `local-only|hybrid|cloud`;
  - `policy_version` (pinned);
  - `budget{wall_s, tokens, usd (optional, null = uncapped but metered), max_sprints, cloud_allowed, allowed_providers, autopilot}`;
  - `composition_level`: `L0|L1|L2` (§9.5);
  - `status`: `queued|running|waiting_gate|draining|stopped`; `stop_reason` is set exactly when the run is stopped;
  - `collect_training_data` (default false), pinned at run start from the training-data setting (§19, D-036).
- `StopReason`: `green|budget_tokens|budget_time|budget_cost|max_attempts|max_sprints|human_abort|unsupported_target|refusal|no_model_available|infra_error`. `no_model_available` means every model in the role's chain, including the local one, is unavailable; the run drains to a resumable checkpoint.
- `RunEvent`:
  - `run_id`, `seq`, `ts`, `ns`, `phase`, `sprint`, `task_id`, `node_id`;
  - `kind`: `phase|node_start|node_end|llm_call|exec|diagnostics|test_result|gate_requested|gate_resolved|escalation|increment|budget|stop|error`;
  - `payload`, `payload_ref`.
- `LLMCallRecord`:
  - `provider`, `model`, `model_hash` (GGUF sha256), `params`, `prompt_hash`;
  - `tokens_in`, `tokens_out`, `tokens_cached`;
  - `latency_ms`, `tok_per_s`, `schema_valid`, `repairs`, `usd`, `stop_reason`.
- `GateRequest{gate_id, kind, run_id, payload, options}` and `GateDecision{gate_id, decision, edits, comment, at}`.

**Training data** (§19, D-036)

- `TrainingAttempt`: `run_id`, `seq`, `recorded_at`, `source` (`run|bench_dev`; the holdout has no value), `target`, `story_kind`, `task_id`, `node_id`, `role` (never `det`), `attempt`, `provider`, `model`, `model_hash`, `local`, `levels` (`LevelResult`s), `improves_on_seq` (an earlier, failed attempt this one retries). Its `verdict` is computed from `levels`: `rejected` if one failed, `accepted` if none failed and at least one passed, otherwise `not_verified` (skipped or unsupported levels confirm nothing).
- `TrainingSample{attempt, prompt_sha256, response_sha256}`: the texts are files referenced by hash, never inline.

## 5. Meta-Agentic Scrum

### 5.1 Mapping

| Scrum concept          | Engine element                                                                      | Persisted artifact                                     |
| ---------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Product Owner          | the user, assisted by `intake` and `refine_backlog`                                 | `project.yaml` / ChangeSpec                            |
| Product backlog        | `refine_backlog`, `test_author`, `architect`                                        | `.barthelona/backlog.yaml`, `contracts.yaml`, `tests/` |
| Scrum Master           | deterministic engine code: budgets, gates, validator, standup, stop reasons         | `runs`, `events`, metrics                              |
| Meta-planner           | `sprint_planner` (proposes) + `compose` + `validate_topology` + `compile`           | `.barthelona/sprints/NN/{plan,topology}.json`          |
| Development team       | roles: architect, test_author, coder, fixer, localizer, reviewer                    | patches, diagnostics                                   |
| Sprint (timebox)       | a compiled sprint subgraph under `SprintBudget`                                     | checkpoints, events                                    |
| Daily scrum            | `standup` after each task layer                                                     | standup events                                         |
| Definition of Done     | `verify_dod`: required ladder level per target and story kind                       | `VerificationReport`                                   |
| Increment              | the integrated green state, committed and tagged `inc-NN`                           | `Increment`                                            |
| Sprint review          | DoD on the integrated increment, contract freeze, gate G3                           | `sprints/NN/review.json`                               |
| Retrospective          | `retro`: metrics plus analysis, producing lessons, overlay knobs and policy patches | `sprints/NN/retro.json`                                |
| Sprint Assembly Policy | immutable policy versions plus a per-project overlay                                | policy store                                           |

The draft's "pool of ready micro-agents" is the **node registry** (§10). The "Binary Contract" is a `Symbol` in the registry. The "Mock Stub" is the pair of generated assembly stubs and Python emulator mocks.

### 5.2 Human gates

| Gate                 | When                                                                  | Decision                                                                                            |
| -------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| G0 Clarify           | after intake, only if needed; at most 5 questions, asked once         | answers, or "proceed with the stated assumptions"                                                   |
| G1 Spec & tests      | before any code is written                                            | approve or edit the spec, requirements and acceptance tests                                         |
| G2 Contracts         | after `architect`, and again on any change to a frozen contract       | approve or edit the contracts. Merged into G1 for single-module projects.                           |
| G3 Sprint review     | end of each sprint                                                    | accept, return items, or stop. Accepted automatically when the sprint is green and autopilot is on. |
| G4 Final             | end of the run                                                        | merge, export, or discard                                                                           |
| G5 Consent & help    | cloud escalation, budget extension, a stuck task (escalation step E4) | allow or deny; or give a hint, change a test via `contract_change`, descope, abort                  |
| G6 Policy activation | after a Policy Lab result                                             | activate, reject, or roll back                                                                      |

- Gates are LangGraph `interrupt()` calls inside dedicated `human_gate` nodes.
- These nodes make no LLM calls, because a node re-runs from its first line when resumed (https://docs.langchain.com/oss/python/langgraph/interrupts).
- A gate shows only artifacts that are already persisted.

### 5.3 Pattern map

Barthelona is a composition of standard agentic patterns. The vocabulary below is used in prompts, ADRs and code comments, so "which pattern is this?" always has one answer.

| Pattern                                       | Where it lives                                                              | Notes                                                                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Hierarchical decomposition / planner–executor | `refine_backlog` → stories → `sprint_planner` → tasks → worker nodes        | The plan is data (backlog, `SprintPlan`), never a chat transcript.                                                   |
| Coordinator (router)                          | `ToolchainResolver`, template choice per story kind, model routing per role | Routes to a dialect/target specialist and a model tier; deterministic where possible.                                |
| Sequential                                    | Template bodies (context → code → apply → gates → ladder)                   | The default shape inside a task.                                                                                     |
| Loop                                          | Fix loops, repair loops, sprint loop                                        | Every loop declares max iterations, wall time, token/cost budget, a success condition and a failure path (§8, §9.5). |
| Parallel                                      | `Send` fan-out over a task layer; `candidates` (best-of-N)                  | Best-of-N is ranked by the oracle, never by an LLM's opinion.                                                        |
| Verifier-gated                                | The verification ladder V0–V8, tamper and minimality gates                  | The central pattern: tools decide acceptance (§13).                                                                  |
| Review & critique / reflexive                 | `llm_review` slot (advisory), `retro`                                       | Runs after deterministic checks, and can block only when a tool confirms the finding.                                |
| Human-in-the-loop                             | Gates G0–G6 (§5.2)                                                          | Required for spec/tests, contracts, final merge, cloud consent and policy activation.                                |
| ReAct (tool loop)                             | Not used by MVP roles                                                       | LLMs produce text; engine code calls tools. May be added for gated research (Phase 5).                               |
| Swarm / debate                                | Not used                                                                    | Expensive and hard to terminate; evidence does not show gains over sampling plus voting (D-025).                     |
| Custom logic                                  | Scrum Master code: budgets, stall detection, escalation, standup            | Deterministic glue between the patterns above.                                                                       |

Retrieval patterns (§14): exact lookup first (instruction, directive and syscall tables), then keyword search (SQLite FTS5 BM25) in the MVP; hybrid keyword + dense search in Qdrant (RRF fusion, optional reranking) only after the Phase 3 retrieval eval shows a gain. The source (facts, dialect docs, project repo map, lessons, and — gated, Phase 5 — the web) is chosen by deterministic rules from the error tokens and the task kind, not by an LLM router. The contract registry plus the repo map act as a deterministic "graph RAG": the graph is parsed from code, not generated by an LLM.

## 6. Run lifecycle and flows

The outer run graph is fixed code, compiled once when the worker starts:

```
create: intake -> [G0] -> refine_backlog -> test_author(acceptance) -> validate_spec -> [G1]
        -> architect -> validate_contracts -> header_gen -> skeleton_build -> [G2]
        -> SPRINT LOOP -> final_integration -> [G4] -> finalize
edit:   import -> detect_target -> baseline_build -> repo_map -> recover_contracts -> characterize
        -> change_spec -> [G1] -> (contract delta ? [G2]) -> SPRINT LOOP -> [G4] -> finalize
SPRINT LOOP: sprint_planner -> compose -> validate_topology (<=2 repairs, else default template)
        -> persist_topology -> run_sprint -> sprint_review -> [G3] -> retro -> loop | exit
```

### 6.1 Create flow

1. **Queue.** The UI inserts a `runs` row with the preset, `mode=create`, description, profile, budgets, `autopilot` and `cloud_allowed`.
2. **Preflight** (deterministic). The resolver checks that the probed image and executors support the (dialect, target) pair. If not, the run stops with `unsupported_target` and an install hint.
3. **Intake.**
   - Detects the language and normalizes the request into an English goal.
   - Extracts entities: I/O, syscalls, constraints.
   - G0 runs only if the request is ambiguous.
4. **Spec and acceptance tests.**
   - `refine_backlog` produces the `ProjectSpec`, a module sketch, and stories of size XS–M.
   - `test_author` produces acceptance `TestCase`s: golden I/O for programs, call tests for library symbols. For pure functions it also writes a Python reference model.
   - Checks:
     - every requirement has at least one test;
     - the examples agree with the reference model, executed in the emulator child or the sandbox.
5. **G1.** The user edits and approves. The tests become locked, and their hashes are recorded.
6. **Architect.** Produces the modules and `Symbol` contracts. Validators check that:
   - registers are legal for the arch;
   - clobbers are consistent with the ABI (a SysV function with `abi=target` must not clobber rbx, rbp or r12–r15);
   - symbols are unique, each with a single owning module;
   - module imports are acyclic;
   - stack alignment and struct offsets are consistent.
7. **Scaffold** (`header_gen`, deterministic). Writes:
   - `gen/*.inc`;
   - contract-honouring `gen/stubs/*.asm`;
   - `gen/contracts.h`, C harnesses, emulator fixtures;
   - the `Makefile`, `.gitattributes` (LF line endings);
   - `.github/workflows/ci.yml`, `release.yml` and `.github/dependabot.yml` from the target family's templates (D-048; `linux-x64` only until further presets land);
   - then runs `git init` and creates branch `bart/<run_id>`.
8. **Skeleton build.** The all-stub project must pass V0–V2 before any LLM-written code exists. This proves the generators and the toolchain.
9. **G2.**
10. **Sprints** (§7) run until the backlog is done or a cap fires.
11. **Final integration sprint.** Mandatory:
    - only real modules, no stubs;
    - the full ladder, including golden I/O.
12. **G4.** The user sees the diff, ladder evidence and cost, then merges or exports.

### 6.2 Edit flow

1. **Import and isolate.** The folder or git URL is cloned into the workspaces root on branch `bart/<run_id>`. The user's original tree is never modified.
2. **Detect the target.** Directive fingerprints and build files suggest a preset, which the user confirms:
   - `%define` / `global` → NASM;
   - `format …` / `include 'win64a.inc'` → FASM;
   - `.globl` / `.section` → GAS;
   - `PROC` / `ENDP` → MASM.

   An existing Makefile or build script becomes an `external` build recipe that runs inside the sandbox.

3. **Baseline build.** If the project doesn't build, the first story is `fix_build`.
4. **Repo map.**
   - Regex extractors per dialect find definitions, linkage and includes. Local labels are ignored.
   - A reference graph is built from call/jmp/lea operands and includes.
   - Symbols are ranked with Personalized PageRank, biased toward the symbols named in the request (https://aider.chat/docs/repomap.html), and the map is rendered within a token budget.
5. **Recover contracts.** `nm` plus Capstone register-access analysis drafts each symbol's in/out/clobber sets. The drafts are marked `inferred` until the user confirms them at G1/G2.
6. **Characterize.** Current behaviour is frozen as tests:
   - existing tests;
   - golden I/O for entry points, using inputs the user provides;
   - emulator snapshots of exported functions under the recovered contracts.
7. **ChangeSpec and G1.** The user approves:
   - the intent and new acceptance tests;
   - the characterization tests expected to change (marked `superseded`);
   - any expected contract deltas (none by default).
8. **Localize.** A deterministic shortlist is built in priority order: symbols named in the request or errors, then grep hits, then PageRank. `localizer` then picks at most M symbol ids from an enum of that shortlist.
9. **Patch.** The `symbol_patch` pipeline:
   - applies symbol or hunk edits atomically;
   - rejects undeclared edits through the minimality gate;
   - runs the ladder on the affected modules, then the full regression suite (characterization tests minus the superseded ones).
10. **Contract changes** go through the `contract_change` pipeline and G2.

Projects created by barthelona already have contracts and tests, so edits to them skip steps 2 and 5 and most of step 6.

## 7. Sprint lifecycle

**Planning.**

- An item is ready when it is approved, its dependencies are done, and its contracts exist (stubs are acceptable).
- Capacity defaults to at most 3 modules or about 600 new lines per sprint. Later it is calibrated from velocity: green items per sprint and attempts per item.
- Tasks are layered topologically by contract dependencies.
- `sprint_planner` emits a `SprintPlan` with a `TopologyRequest`. How much of the graph the AI composes is set by the composition level (§9.5):
  - **L0 (always available, the fallback):** rule-based. The story kind picks the template, and knobs keep their defaults.
  - **L1 (experimental flag in Phase 1, default from Phase 2 if the bench agrees):** an LLM chooses the template, slot insertions, knob values and per-loop budgets, constrained to enums and bounded numbers.
  - **L2 (Phase 2, strong models only):** an LLM composes each task pipeline directly from registered node types and edges. It is validated by the same rules T1–T10.

**Composition** (deterministic `compose`). Steps:

1. Start from the template, the requested insertions and the knob values.
2. Apply policy rules, e.g. `dialect=fasm ∧ tags∋macro ⇒ insert macro_expand_check at post_apply`.
3. Apply the project overlay.
4. Clamp everything to the caps.

The result is a set of `TaskPipeline`s and one `SprintTopology`.

**Validation.** The rules are in §9.4. On failure, the error list goes back to the planner, at most twice. After that the policy's default template is used and a `validation_exhausted` event (not a stop reason) is logged; the run is never blocked.

**Compilation, persistence and resume.**

- The `SprintTopology` JSON, its `spec_hash` and the `builder_version` are written to `.barthelona/sprints/NN/topology.json` before execution.
- `compile_sprint(topology)` is a pure function: node names are derived from pipeline hashes and NodeSpec ids, and the same input yields the same graph.
- The outer `run_sprint` node rebuilds the graph from the persisted JSON and invokes it as a subgraph, checkpointed in the run thread's namespace. After a crash, the rebuild is identical and LangGraph resumes from the last checkpoint. Resuming requires an unchanged topology (cf. https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).
- `recursion_limit` is derived from the sum of the loop bounds, plus a margin. LangGraph's default is 1000.
- **Spike (Phase 1 exit criterion).** Kill the worker mid-task and again during a gate. Resuming must not re-run finished nodes.
- **Fallback if the spike fails.** A fixed interpreter subgraph walks the same `SprintTopology` data with a cursor in state. The registry, validator and templates do not change.
- **Crash consistency (D-044).**
  - Ownership: the workspace git repository and `.barthelona/` own artifacts and plans; `app.sqlite` owns the operator-visible record (runs, events, gates, commands, ledger); the LangGraph checkpoint owns only the control position (paths and hashes); `var/runs/<id>/llm/` owns recorded model responses.
  - Write order in a side-effecting node: the effect (idempotent, keyed by run, task, attempt, node), then its events (each with a `dedupe_key`, unique per run, so a replayed append is a no-op and the store assigns `seq`), then the checkpoint. A crash in between re-runs the node and every step is a no-op.
  - On resume the gateway reuses the recorded response for the same (node, attempt, prompt hash) instead of calling a provider again.
  - `gate_requested`, `increment` and `stop` events are flushed before the checkpoint; other events keep the 250 ms batch (§17).
  - `Run.engine_state_version` is bumped when the graph state or node semantics change incompatibly. The worker resumes only supported versions; otherwise the run stops with `infra_error` and a new run can start from the last `inc-NN` tag.
  - The spike kills the worker after the effect, after the event, mid-batch and during a gate.

**Execution.**

1. `header_gen` refreshes the generated files, including stubs for dependencies that aren't built yet.
2. For each layer, one LangGraph `Send` per task goes to that task's pipeline node. Results are merged with an `operator.add` reducer.
3. Concurrency is limited by gateway semaphores: one call in flight per local endpoint.
4. State holds only paths and hashes; file contents stay on disk.
5. After each layer, `standup` (deterministic) decides one of:
   - continue;
   - escalate;
   - descope: the item becomes `blocked` and returns to the backlog;
   - re-plan: the planner rewrites the _remaining_ part of the sprint graph (§9.5), bounded by the `max_replans` knob (default 1, cap 3), and through G2 if contracts would change.
6. A stall detector also runs inside every loop: the same `error_sig` twice, a repeated patch hash, or no improvement in tests passed for N iterations. A stall exits the loop early through `exit_escalate`, so the standup can re-plan instead of burning the remaining iterations.

**Review.**

1. `integration` swaps stubs for the real modules that now exist.
2. `verify_dod` runs the DoD ladder.
3. `commit_increment` commits and tags `inc-NN`.
4. Finished symbols are marked `tested` and frozen, and the registry version is bumped.
5. Dependents whose contract hash changed are flagged stale.
6. G3.

**Retrospective.**

Deterministic metrics come first:

- attempts per node and per task;
- a histogram of error signatures;
- escalations;
- tokens, time and dollars;
- schema failures;
- which insertions fired.

The main model then produces a structured analysis:

- **Lesson candidates:** only with evidence that a failure became a pass (§15.2).
- **Overlay changes:** knob values within the policy's declared ranges, and the allowed insertions for tagged task classes. They apply from the next sprint and are logged and revertible. Examples:
  - `max_fix_iters 3→4 for dialect=nasm`;
  - `insert abi_lint at post_apply for tasks tagged stack`.
- **Policy patch proposals:** queued for the Policy Lab, never applied in-run.

This is the Gemini draft's "Sprint Assembly Policy" made safe: the retrospective does change how future sprints are assembled, but only through validated, logged, reversible channels.

## 8. Loops, budgets, escalation

| Loop                                                    | Default                                                                                                                   | Cap               | On exhaustion                                                  |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------- |
| G0 clarify                                              | 1 round                                                                                                                   | 1                 | proceed with the stated assumptions                            |
| Structured-output repair, per call                      | 2                                                                                                                         | 2                 | next tier, then a deterministic fallback or the human          |
| Topology repair                                         | 2                                                                                                                         | 2                 | default template                                               |
| Fix loop, per task per escalation step                  | 3                                                                                                                         | 4                 | next escalation step                                           |
| Stall: same `error_sig` twice, or a repeated patch hash | —                                                                                                                         | —                 | jump to the next escalation step                               |
| Candidates (only after a failure)                       | 2 locally                                                                                                                 | 3 local / 5 cloud | next escalation step                                           |
| Re-plan (`max_replans` knob)                            | 1 per sprint                                                                                                              | 3 (policy cap)    | descope the item                                               |
| Sprints per run                                         | 10                                                                                                                        | policy cap        | stop and report                                                |
| Wall clock / tokens / USD                               | per profile (`budget.limits_by_profile` in `config/models.yaml`; 4 h by default) / per profile / unlimited (optional cap) | run settings      | drain to a resumable checkpoint, then offer an extension at G5 |
| Per-loop budget (any unit)                              | set per loop by the planner (§9.5)                                                                                        | policy caps       | the loop's `on_exhaust` edge                                   |

The dollar budget is optional. When no cap is set, spending is still metered per call, per sprint and per provider and shown in the UI, so the owner always sees what a run costs. Running out of provider credit is handled as a provider failure (§16.6), not as a budget stop.

**Escalation ladder per task:**

- **E0:** retry with structured diagnostics (the first error ±5 lines).
- **E1:** enrich the context with:
  - exact facts for the error's tokens;
  - lessons matching the error signature;
  - docs filtered by the error's terms;
  - the code of called functions.
- **E2:** the `candidates` pipeline. 2–3 variants regenerated from the contract and ranked by the oracle.
- **E3:** the role's cloud escalation chain from `config/models.yaml` (any enabled provider, in the configured order), only if `cloud_allowed`. Unavailable providers are skipped by the circuit breaker (§16.6).
- **E4:** the human, via G5.

An unsatisfiable contract goes to `contract_change` and G2.

**Runtime mechanisms:**

- LangGraph per-node async `timeout`;
- `RetryPolicy` only for transient I/O (connection errors, timeouts);
- `RunControl.request_drain()` for cancellation and budget stops, leaving a resumable checkpoint;
- `durability="sync"` checkpoints.

## 9. Topology DSL

### 9.1 Concepts

- **Node type:** a registry entry (§10).
- **Template:** a versioned task pipeline in `policies/vN/templates/*.yaml`.
- **Slot:** a named insertion point that accepts only its listed optional node types.
- **Knob:** a typed parameter with a range and a default. Caps are absolute ceilings.
- **TaskPipeline:** a template expanded with its insertions and knob values. Its fields are `nodes[NodeSpec{id, type, params, role, timeout_s}]`, `edges[EdgeSpec{src, dst, when: ok|fail|always}]`, `loops[LoopBound{back_edge, max_iters, max_wall_s, max_tokens, max_usd, on_exhaust, stall}]`, `entry`, `exits_ok`, `exits_fail`, `max_llm_calls` and `hash`.
- **SprintTopology:**
  - `sprint_no`, `policy_version`, `builder_version`;
  - `pre`: `[header_gen]`;
  - `layers`;
  - `pipelines`: map of hash to TaskPipeline;
  - `task_pipeline`: map of task id to hash;
  - `post`: `[integration, verify_dod, review_gate]`;
  - `budget`, `spec_hash`;
  - `revision` (K in `topology.rK.json`) and `composition_level` (the level actually used).

### 9.2 Template example (`module_create`; illustrative: the `abi_lint` insertion and the `trace_capture` slot arrive with policy v2)

```yaml
id: module_create
version: 1
applies_to: [create_module, implement_symbol]
knobs:
  max_fix_iters: { type: int, min: 1, max: 4, default: 3 }
  context_profile: { type: enum, values: [8k, 16k, 32k], default: 16k }
  temperature: { type: float, min: 0.0, max: 0.3, default: 0.1 } # applied to local models only (§16.3)
slots:
  pre_code: { after: ctx, allowed: [unit_test_author, doc_digest] }
  post_apply:
    { after: tamper, allowed: [macro_expand_check, abi_lint, llm_review] }
  on_fail: { after: ladder.fail, allowed: [trace_capture] }
nodes:
  - { id: ctx, type: context_build, params: { profile: $context_profile } }
  - { id: code, type: codegen, role: worker }
  - { id: apply, type: apply_patch }
  - { id: tamper, type: tamper_gate }
  - { id: ladder, type: ladder, params: { up_to: dod } }
  - { id: triage, type: triage }
  - { id: fix, type: fixer, role: worker }
  - { id: ok, type: exit_ok }
  - { id: esc, type: exit_escalate }
edges:
  - [ctx, code, always]
  - [code, apply, ok]
  - [code, esc, fail]
  - [apply, tamper, ok]
  - [apply, triage, fail]
  - [tamper, ladder, ok]
  - [tamper, triage, fail]
  - [ladder, ok, ok]
  - [ladder, triage, fail]
  - [triage, fix, always]
  - [fix, apply, ok]
  - [fix, esc, fail]
loops:
  - {
      back_edge: [fix, apply],
      max_iters: $max_fix_iters,
      on_exhaust: esc,
      stall: same_error_sig_twice,
    }
entry: ctx
```

Inserted nodes are spliced in as a linear chain: `ok` goes to the next node, `fail` goes to `triage`.

### 9.3 Template catalogue

The target catalogue below is delivered across immutable policy versions: **v1** (Phase 1) ships `module_create`, `symbol_patch`, `fix_build`, a minimal `contract_change` and `integration`; **v2** (Phase 2) adds `candidates` and the `trace_capture` slot; later versions refine them. A released version never gains templates (D-018).

| Template                     | Used for                                           | Shape                                                                                                           |
| ---------------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `module_create`              | create_module, implement_symbol                    | context → FILE block → apply → tamper → ladder → fix loop                                                       |
| `symbol_patch`               | fix_bug, change_behavior, refactor, edit-mode work | localize → context → symbol/hunk edits → apply → tamper → minimality → ladder + regression → fix loop           |
| `fix_build`                  | baseline failures                                  | build → triage → patch loop                                                                                     |
| `candidates`                 | escalation step E2, or stories tagged hard         | N diverse variants in separate workdirs → all through the ladder → rank: tests passed, then warnings, then size |
| `contract_change`            | registry deltas                                    | propose → G2 → regenerate → re-verify dependents                                                                |
| `integration` (sprint-level) | every sprint end, plus the final sprint            | swap stubs → full ladder → golden I/O                                                                           |

### 9.4 What the planner may request, and validation

**Grammar.** A `TopologyRequest` may only:

- choose a `template_id` that applies to the story kind;
- pick insertions from each slot's `allowed` list, at most 2 per slot;
- set knob values within their ranges;
- set per-loop budgets within the policy caps, and the unit size (L1);
- at L2 only: supply whole `TaskPipeline`s whose node types, params and edges come from the registry (§9.5).

Its JSON schema is generated from the active policy as enums, so constrained decoding cannot produce out-of-vocabulary output.

**Validator** (`engine/sprint/validate.py`, using networkx). Every rule must pass:

- **T1 Vocabulary.** Every node type is registered and supported for the dialect and target. Params validate against the type's `Params` model.
- **T2 Identity.**
  - Ids match `^[a-z][a-z0-9_]{0,31}$` and are unique.
  - `spec_hash` is the sha256 of the canonical JSON.
- **T3 Structure.**
  - Exactly one entry.
  - Every node is reachable from the entry and can reach an exit.
  - Exits have no outgoing edges.
- **T4 Totality.** Every non-exit node has edges covering all its declared outcomes, with no duplicates.
- **T5 Bounded cycles.**
  - Every strongly connected component contains exactly one declared back-edge.
  - Removing the back-edges leaves a DAG.
  - `max_iters` is within the cap (default 4).
- **T6 Verification dominance.**
  - `ladder(up_to=dod)` dominates every `exit_ok`.
  - Every path from `apply_patch` to `exit_ok` passes through `tamper_gate`, and through `minimality_gate` in edit mode.
- **T7 Write scopes.**
  - The union of the nodes' write scopes stays within the task's scope.
  - No node writes protected paths: `tests/**`, `contracts.yaml`, `project.yaml`, `gen/**` (except `header_gen`), or `.barthelona/policy*`.
- **T8 Budget.**
  - Worst-case LLM calls ≤ the task budget. Worst case = Σ over LLM nodes of (calls × the product of enclosing loop bounds).
  - The sum over tasks ≤ the sprint budget.
  - The token estimate ≤ the token budget.
- **T9 Role and consent.** Every node's role (`det`, `main`, `planner`, `worker`, `cheap`, `escalation`) is allowed for the run. A role reaches models only through the run's profile chain (§16.2), and cloud entries of a chain are used only when `cloud_allowed` is set. L2 pipelines may not raise a node's role above its registry `max_role`.
- **T10 Gate hygiene.** `human_gate` nodes make no LLM calls.

**Property tests** (Hypothesis):

- Random graphs, and mutations of valid ones, must be rejected. Mutations include an unbounded cycle, a dropped ladder, an exceeded budget, and a write to `tests/`.
- Every catalogue template expanded with every legal combination of insertions must pass.

### 9.5 AI-composed sprint graphs

The owner's requirement: the system must not push every task through one fixed graph. For each unit of work, the AI forms the loop graph it needs from ready-made pieces, and it reshapes that graph when reality disagrees with the plan. This section defines how, without giving up termination or verification guarantees.

**Ready-made pieces.** Node types in the registry (§10) are written in code and tested. Templates (§9.3) are pre-assembled, vetted pipelines of those nodes. The AI never invents node types or writes executable code for the engine.

**Composition levels.** Each run has a maximum level (`planner.composition_level`), and each sprint records the level it actually used.

| Level | Who composes              | What may vary                                                              | When                                                                                  |
| ----- | ------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| L0    | Rules                     | Template chosen by story kind; default knobs                               | Always available; the fallback after failed validation                                |
| L1    | LLM, constrained decoding | Template choice, slot insertions, knob values, per-loop budgets, unit size | Experimental in Phase 1; default from Phase 2 if the bench shows no regression        |
| L2    | LLM, strong tier only     | Whole task pipelines: any registered node types, edges and loops           | Phase 2, behind a flag; enabled per profile only after the bench shows a gain over L1 |

At L2 the planner emits `TaskPipeline` objects directly (nodes, edges, loops). The JSON schema for that output is generated from the registry, so node types are enums. The same validator rules T1–T10 apply. In particular, T6 (every `exit_ok` is dominated by the DoD ladder) and T5 (every cycle has exactly one declared, bounded back-edge) make an "AI-designed" pipeline as safe as a template.

**The unit of a loop.** Every `LoopBound` may set any combination of four units, and the loop stops at whichever fires first:

- **logical:** the success edge (e.g. the ladder reaches the DoD level);
- **count:** `max_iters`;
- **time:** `max_wall_s`;
- **tokens / money:** `max_tokens`, `max_usd`.

The planner also chooses the size of the unit of work itself (one symbol, one module, or a module group) from the model tier, the story size and the measured velocity. Weaker models get smaller units and tighter loops.

**Re-planning mid-sprint.** When a loop exits through `exit_escalate`, the sprint does not simply fail. The flow is:

1. The standup sends the planner the remaining tasks, the stalled task's diagnostics summary, and the current budgets.
2. The planner returns a revised `TopologyRequest` (or, at L2, revised pipelines) for the _remaining_ work only. It may:
   - insert a `doc_digest` or `trace_capture` node;
   - switch to the `candidates` template;
   - split the story into smaller stories;
   - move to the next model tier;
   - ask the human (G5).
3. The revision is validated, persisted as `sprints/NN/topology.rK.json` with a new `spec_hash`, and compiled.

Re-planning is bounded by `max_replans`. Resume after a crash uses the latest persisted revision.

**Across sprints.** The retrospective may change knob defaults and allowed insertions for the next sprint (overlay), and may propose policy patches (Policy Lab). Both channels are bounded and reversible (§11).

**Fallbacks.**

- An invalid proposal gets the validator's error list and at most 2 repair attempts, then L0.
- A model that repeatedly fails to compose drops to L0 for the rest of the run, and the event is logged.
- The UI shows, for every sprint, the level used, the graph (DOT), and the planner's rationale.

## 10. Node registry

**Registries (D-053):** roles, dialects and targets, provider backends, tools and checks are registries of string-keyed entries that declare their own metadata, validated at load time; core code never branches on a concrete id. The node registry below is one instance. Planned for Phase 1b (F-86).

**Registry entry fields:**

- `type`, a `Params` model, `reads` and `writes` (state keys);
- `write_scope` globs, `outcomes`, `max_role` (the highest role the node may run under), `dialects`;
- `est_llm_calls`, `est_tokens`, `idempotent`, `timeout_s`;
- `retry`: transient errors only.

Side effects are idempotent, keyed by run, task and attempt.

| Type                                                                             | Purpose                                                                                             | Role                             | Writes                                            |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------- |
| intake                                                                           | detect language, normalize to English goal, extract entities, ask questions                         | main                             | —                                                 |
| refine_backlog                                                                   | spec, requirements, stories                                                                         | planner                          | backlog draft                                     |
| test_author                                                                      | acceptance tests and reference models                                                               | planner                          | `tests/` (before the freeze only)                 |
| architect                                                                        | modules and contracts, or a contract delta                                                          | planner                          | contracts draft (before the freeze)               |
| validate_spec, validate_contracts                                                | semantic checks                                                                                     | det                              | —                                                 |
| header_gen                                                                       | `.inc` files, stubs, `contracts.h`, harnesses, fixtures, Makefile                                   | det                              | `gen/`                                            |
| skeleton_build                                                                   | V0–V2 on the stubs                                                                                  | det                              | `build/`                                          |
| sprint_planner                                                                   | SprintPlan + TopologyRequest (L0–L1) or TaskPipelines (L2); also re-plans the remainder of a sprint | det (L0), planner tier (L1–L2)   | `plan.json`, `topology.rK.json`                   |
| compose, validate_topology, compile                                              | §9                                                                                                  | det                              | `topology.json`                                   |
| context_build                                                                    | prompt bundle within the token budget                                                               | det                              | `var/runs`                                        |
| doc_digest (slot)                                                                | condense retrieved docs for the task                                                                | main                             | —                                                 |
| unit_test_author (slot)                                                          | per-symbol tests from the contract; must compile against stubs; then locked                         | main                             | `tests/unit` (for that symbol, before coding)     |
| codegen                                                                          | one whole module as a FILE block                                                                    | worker                           | the task's own source path                        |
| patcher                                                                          | symbol or hunk edits                                                                                | worker                           | the task's source paths                           |
| apply_patch                                                                      | parse the envelope, path fence, atomic apply or revert                                              | det                              | task scope                                        |
| tamper_gate                                                                      | protected files unchanged; regenerated `gen/` byte-identical                                        | det                              | —                                                 |
| minimality_gate                                                                  | edits only inside declared symbol spans or files                                                    | det                              | —                                                 |
| macro_expand_check (slot)                                                        | preprocess-only output (`nasm -E`, fasm pass limits), include-case lint                             | det                              | —                                                 |
| ladder                                                                           | V0 up to the DoD level                                                                              | det                              | `build/`                                          |
| abi_lint (slot)                                                                  | early V3 check                                                                                      | det                              | —                                                 |
| triage                                                                           | normalize diagnostics, `error_sig`, FixBrief with lessons and facts                                 | det                              | —                                                 |
| fixer                                                                            | FixBrief + file → hunks                                                                             | worker → escalation              | task scope                                        |
| candidates                                                                       | N variants, ranked by the oracle                                                                    | worker / cloud                   | scratch workdirs                                  |
| llm_review (slot, advisory)                                                      | findings and proposed tests; blocks only when a tool confirms the finding                           | worker                           | —                                                 |
| trace_capture (slot)                                                             | V7 gdb/qemu trace for the fixer                                                                     | det                              | `var/runs`                                        |
| localizer                                                                        | at most M symbol ids from the shortlist enum                                                        | main                             | —                                                 |
| standup                                                                          | decision after each layer                                                                           | det                              | —                                                 |
| integration, verify_dod, commit_increment                                        | sprint review steps                                                                                 | det                              | `build/`, git                                     |
| retro                                                                            | metrics + analysis                                                                                  | planner / main                   | `retro.json`, candidate lessons, proposed patches |
| human_gate                                                                       | `interrupt()`                                                                                       | human                            | —                                                 |
| exit_ok, exit_escalate, exit_fail                                                | terminals                                                                                           | —                                | —                                                 |
| import, detect_target, baseline_build, repo_map, recover_contracts, characterize | edit-mode preparation                                                                               | det (main breaks detection ties) | `.barthelona/`                                    |

"det" means deterministic code with no LLM. Roles map to models through the profile chains (§16.2).

## 11. Policy and self-improvement

**Policy versions.**

- Layout: `policies/vN/` holds `templates/`, `prompts/<role>.md.j2`, `rules.yaml` (composer rules), `knobs.yaml` (ranges and defaults), `caps.yaml`, and `MANIFEST.json` (sha256 of every file, `released: true`).
- `policies/v1/` is the seed and is tracked in git.
- Versions created at runtime live in `var/policies/vN/`. `barthelona policy export vN` copies one into the repo for committing.
- Released versions are immutable. A test enforces this, and so does a Claude Code hook.
- Each run pins a version. The active version is a pointer in `app.sqlite`, so a rollback just moves the pointer.

**Three channels of change:**

1. **Overlay** (in-run, per project). Bounded knob and insertion changes from the retrospective, revertible in the UI.
2. **Policy patch** (offline). JSON Patch proposals against vN go to the **Policy Lab**:
   - the Lab builds candidate vN+1;
   - runs A (active) against B (candidate) on the same tasks and models, at least 3 repeats each. Local runs go overnight; cloud runs use the Batch API at 50% off;
   - accepts B only if:
     - its holdout solve rate is at least A's;
     - no task flips from pass to fail in the majority of repeats;
     - the target metric improves by at least a threshold;
     - cost stays within the cap;
   - then the change goes to G6. Automated workflow search only works against a benchmark (https://arxiv.org/abs/2410.10762).
3. **Lessons** (§15.2). These change knowledge, not workflow.

**Invariants that no overlay or patch can change.** They are enforced in `policy/invariants.py` and by tests:

- DoD dominance, and the tamper and minimality gates;
- protected paths;
- the sandbox profile;
- loop caps and budget ceilings;
- gates G1, G2, G4 and G5;
- hidden tests never enter prompts;
- `human_gate` nodes make no LLM calls.

## 12. Toolchain layer

**Protocols** (`toolchains/`, `executors/`):

- `Dialect` (planned, Phase 1+):
  - attributes: `id`, `exts`, `comment_prefix`, `local_label_re`;
  - `targets()`, `tools(target)`;
  - `syntax_check(src, target)`, `assemble(src, out, target, defines)`, `preprocess(src, target)`. Each returns a `Command`;
  - `parse(result, workdir) -> list[Diagnostic]`;
  - `includes(text)`;
  - `render_interface(registry, module)`, `render_stub(symbol)`.
- `DialectAdapter` (**Phase 0 subset**, `toolchains/dialect.py`): a structural Protocol that covers only
  the commands needed by the verification ladder (V0–V2). It returns raw argv tuples
  (`tuple[str, ...]`) instead of full `Command` objects; the ladder passes them to the session,
  and the `tc` executor wraps them in `docker exec bart-tc`. Method names differ from the planned
  `Dialect` protocol intentionally: `syntax_check_argv`, `assemble_argv`,
  `parse_diagnostics`. When `contracts.yaml` and the full target abstraction land,
  `DialectAdapter` will be superseded by `Dialect`; adapters will be migrated to accept
  the `target: TargetProfile` and `defines: Mapping[str, str]` parameters and return
  `Command`.
- `Linker`: `link(objs, out, target, kind)` and `parse(...)`.
- `Executor` (D-043, implemented in `executors/`: `Executor`/`Session` protocols, `AgentExecutor`, `WslTransport`, `LocalTransport`, `FakeExecutor`):
  - `id`: `tc`, `sandbox`, `emu`, or (later) `windows-native`;
  - `may_run_untrusted`;
  - `async open_session(run_id, attempt) -> Session` and `async image_digest(image)` (the probe runs tool `--version` commands through a session); a `Session` owns one work directory and offers `async stage(tar)`, `async run(cmd, limits) -> ExecResult`, and `async collect()`;
  - the executor owns its environment: callers pass the tool argv and the `tc` executor wraps it in `docker exec bart-tc`;
  - `AgentExecutor(transport)` with `WslTransport` (Windows) and `LocalTransport` (Linux host with Docker, same agent and allow-list); the agent protocol carries a request `id` on every message, handles requests concurrently and starts with a versioned `hello`.
- `Command` is an argv tuple plus `cwd`, `env`, `stdin` and `timeout`. Shell strings never appear anywhere.
- `ToolchainResolver.plan(dialect, target) -> BuildPlan` picks executors that have every required tool. The result of `probe()` is written to `config/toolchains.lock.json`: the image digest and each tool's `--version`.

**MVP presets** (`config/targets.yaml`):

- `linux-x64-nasm-static`: `nasm -f elf64 -g -F dwarf -Xgnu -w+error`, then `ld`.
- `linux-x64-nasm-libc`: gcc links.
  - Ubuntu's gcc builds PIE by default, so the NASM rule card requires `default rel` and `call fn wrt ..plt`.
  - The preset may instead link with `-no-pie`.
- `linux-x64-gas-intel-static` and `linux-x64-gas-intel-libc`: `.intel_syntax noprefix`, then `as --64 -g --fatal-warnings`.
- `linux-x64-gas-att-static` and `linux-x64-gas-att-libc`.
- Every template emits a `.note.GNU-stack` section, because ld 2.39 and later warns without it.

**Later presets:**

- FASM 1: `format ELF64 executable 3` and `format PE64 console`, both output directly without a linker.
- Win64:
  - NASM `-f win64` with mingw, tested under wine in Docker;
  - FASM PE64.
- ELF32 cdecl: needs `libc6-dev-i386` and `lib32gcc-15-dev`, not `gcc-multilib`, which conflicts with the cross compilers.
- asmc and UASM (MASM syntax on Linux).
- ml64 on Windows: needs the VS Build Tools, which require admin rights.
- Boot sectors via `qemu-system`.
- AArch64 and RISC-V via `qemu-user`.

The UI greys out presets that fail the resolver check and shows the reason.

**Diagnostics.** Per-tool regexes:

| Tool                | Format matched                        |
| ------------------- | ------------------------------------- |
| NASM/YASM `-Xgnu`   | `file:line: severity: msg [-w+class]` |
| GAS                 | `file:line: Error\|Warning:`          |
| MASM-family         | `file(line) : error A####:`           |
| ld                  | `file:(section+0x..): msg`            |
| link.exe / lld-link | `LNK####`                             |

FASM needs a line-based state machine:

- frame lines look like `file [line] macro [mline]:` and are followed by `error: …`;
- FASM 1 reports only the first error;
- fasmg reports more with `-e N`.

Normalization:

- Paths are reverse-mapped to project-relative paths. Non-greedy `.+?` before `:line:` keeps Windows drive letters intact.
- `error_sig` is a hash of the tool, the code, and the message with paths, line numbers, symbols and numbers replaced by placeholders.

**Windows ↔ WSL bridge.**

- **One agent process.** The worker copies the agent file from the repository to `~/.local/share/barthelona/agent.py` in the distro on every start (written to a temp file, then moved into place), then starts it with `wsl.exe -d Ubuntu -e sh -c 'exec python3 -u "$HOME/.local/share/barthelona/agent.py"'` (`-e` has no shell, so `~` would not expand). It speaks JSON lines; binary data is base64; `WSL_UTF8=1` is set.
- **Staging.** The worker tars sources, `gen/`, tests and the Makefile, and the agent extracts them to `~/.cache/barthelona/runs/<run>/<attempt>/` on ext4. `/mnt/c` is a slow 9P share, so it is never used. Artifacts are tarred back.
- **Agent allowlist:**
  - `docker exec bart-tc …`;
  - `docker run … bart-run …`, with the sandbox flags (including the `--ulimit`s and `-i`) fixed by the agent, not by the caller. The only caller-supplied option is a `mount` request field: a directory under the cache root that the agent bind-mounts read-only at `/work`. The agent never leaves its own stdin attached to a child;
  - `docker inspect --format … <image>` — exactly one target, restricted to `bart-tc` or `bart-run*` (used by `barthelona probe` to record image digests);
  - `tar`, `sha256sum`.
  - Every path must be under `~/.cache/barthelona/`.
- **Text hygiene:**
  - Generated files are written with `newline="\n"`.
  - Projects ship `.gitattributes` with `* text=auto eol=lf`.
  - A lint checks the case of include paths, because NTFS is case-insensitive and ext4 is not.
  - `wsl.exe -l` prints UTF-16 unless `WSL_UTF8=1` is set.
- **Health.**
  - The worker checks `wsl.exe -l --running` and starts the VM lazily.
  - It warms up the agent and `bart-tc`.
  - Docker and Qdrant failures show banners in the UI instead of crashing a run.
- **Loopback address.** Local endpoints use `127.0.0.1`, never `localhost`. On this machine `localhost` resolves to `::1` first; LM Studio listens on IPv4 only, so requests to `localhost:1234` hang until the client timeout, while `127.0.0.1:1234` answers in about 0.25 s (measured 2026-10-13).

**Images.**

- `docker/toolchain/Dockerfile`:
  - based on `ubuntu:26.04`, pinned by digest;
  - nasm (3.01 from apt; the local docs describe 3.02), yasm, fasm 1.73.34, binutils 2.46, gcc 15, libc6-dev, make, gdb, file;
  - runs as user 65534.
- `docker/runner/Dockerfile`: a minimal `ubuntu:26.04` with libc6 and a batch test-runner script. Static qemu-user is added later.
- Wine goes in a separate image.

## 13. Verification ladder, Definition of Done, sandbox

### 13.1 Ladder (cheapest first)

| Level | Check                                                                                                                  | Typical cost       | Where           |
| ----- | ---------------------------------------------------------------------------------------------------------------------- | ------------------ | --------------- |
| V0    | Syntax only (`nasm -o /dev/null`, `as -o /dev/null`)                                                                   | 10–100 ms          | bart-tc         |
| V1    | Assemble every module; compare `nm` symbols with the registry: exports exact, undefined symbols ⊆ imports ∪ allow-list | <1 s               | bart-tc         |
| V2    | Link: unresolved or duplicate symbols, PIE relocations, entry point                                                    | <1 s               | bart-tc         |
| V3    | Static ABI lint over a Capstone CFG                                                                                    | <1 s               | emulator child  |
| V4    | Unicorn unit tests plus dynamic ABI contract checks                                                                    | 10–500 ms per case | emulator child  |
| V5    | C-harness tests (gcc; later mingw + wine)                                                                              | 1–3 s              | bart-run        |
| V6    | Whole-program golden I/O; qemu-user or qemu-system later                                                               | 1–10 s             | bart-run        |
| V7    | gdb or qemu trace, only after a failure, as context for the fixer                                                      | seconds            | bart-run        |
| V8    | Real Windows (Windows Sandbox), opt-in, later                                                                          | 30–60 s            | Windows Sandbox |
| T, M  | Tamper gate after every apply; minimality gate in edit mode                                                            | ms                 | worker          |

**Levels are registered checks (D-046).** The ids V0 to V8 are stable names; each is implemented by a `LevelCheck` (`level`, `supports(ctx)`, `async run(ctx)`) registered per target family, so a family such as WebAssembly can supply its own V3 or V4. `run_ladder` walks the registry in order: an unsupported level returns `unsupported` with a reason, a failed level makes later ones `skipped`, and a required level that is not `pass` means the work is not done. Checks take the whole module list; batching their commands is follow-up F-52. With a contract registry, V1 compares `nm -P -g` output with it: a module's defined globals must equal its registry exports, and its undefined symbols must be the `calls` of its symbols, `extern` registry symbols, or the allow-list. V6 runs each `io_golden` `TestCase` (`inputs.stdin`, `expect.stdout`, `expect.exit_code`, default exit code 0) against `output.elf` through the sandbox executor; without a sandbox executor or golden cases it is `unsupported`. V5 builds each `c_harness` case's generated `gen/harness/<id>.c` with gcc in the toolchain container, linked with the project's objects except the entry module, and runs it in the sandbox; it needs contracts, a sandbox executor and at least one case, else it is `unsupported`. `run_ladder` takes its optional inputs as a `LadderOptions` dataclass and stages the generated `gen/` files next to the sources when contracts are given. `dod_satisfied(required, results)` takes the required levels from the caller, so the MVP set (V0–V2, V5, V6) can leave out V3/V4 until Phase 2.

**Implementation approach:** See D-056 for the V3/V4 emulator design. V3 uses Capstone for static CFG analysis; V4 uses Unicorn for dynamic emulation. Both live in `src/barthelona/emulator/` (the emulator child package). V4 runs **only for mutation-corpus kinds that V3 + V5 canary cannot detect** (#102).

V3 checks:

- the rsp delta along every path; stack balanced at every `ret`;
- alignment ≡ 8 (mod 16) at every call;
- callee-saved registers saved and restored;
- reads of rcx/r11 after `syscall`;
- absolute 32-bit references in PIE code;
- `.note.GNU-stack` present;
- `vzeroupper` before returning from AVX code;
- Win64 later: shadow space ≥ 32 bytes, and a `.pdata` entry for every non-leaf function.

**How V4 works:**

1. **Image.** Link the module at a fixed base (`ld -Ttext=… --defsym <import>=<trap>`) inside `bart-tc`, then load the segments with pyelftools.
2. **Memory.** The stack has guard pages on both sides. On entry, `rsp ≡ 8 (mod 16)`, and the return address points to a trap.
3. **Canaries.** Callee-saved registers are seeded with canaries:
   - SysV: rbx, rbp, r12–r15;
   - Win64: those plus rdi, rsi and xmm6–15.
4. **Hooks:**
   - **Calls:** alignment at each call site found by a Capstone pre-pass; Win64 shadow space.
   - **Memory writes:** the red zone, the return-address slot, anything outside declared buffers.
   - **Syscalls and interrupts:** an allow-list only — `write` goes to captured stdout, plus `exit`.
5. **Imports.** Calls to imports are served by Python mocks generated from the registry. These are the draft's "mock stubs between sprints", made executable.
6. **Limits.** An instruction-count cap and a microsecond timeout.
7. **Error mapping.** A faulting PC is mapped to `file:line` through DWARF (`-g -F dwarf` for NASM, `-g` for GAS).
8. **AVX.** Unicorn rejects 256-bit VEX instructions. A setup probe confirms this, and such code is routed to V5.

**ABI mutation corpus** (`tests/abi_mutation/`). For each violation kind and each MVP dialect there is a good snippet and a bad one. Kinds:

- misaligned call;
- clobbered callee-saved register;
- unbalanced push/pop;
- red-zone write;
- DF left set;
- missing shadow space;
- PIE absolute reference;
- reading rcx after `syscall`;
- missing `.note.GNU-stack`.

V3 and V4 must flag 100% of the bad snippets with 0 false positives on the good ones. This is the Phase 2 exit criterion, and it must hold before any agent result is trusted.

### 13.2 Definition of Done (linux-x64 MVP presets)

| Story kind                  | Required for green                                                        |
| --------------------------- | ------------------------------------------------------------------------- |
| library symbol or module    | MVP: V0–V2 + V5. From P2: V0–V5, including the V3 lint and V4 ABI checks. |
| program entry / integration | V0–V2, V5, V6 (+ V3/V4 from P2)                                           |
| edit stories                | the above plus a clean characterization regression and the M gate         |
| contract_change             | the above for every dependent module                                      |
| all                         | T gate after every apply                                                  |

Later targets:

| Target           | Required                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------- |
| Win64 PE         | V0–V4, plus V5 under wine                                                                                            |
| ml64             | V0–V4 on windows-native                                                                                              |
| Boot sector      | V0, size == 512, last two bytes `0x55AA`, plus V6 on qemu-system via the serial port and the `isa-debug-exit` device |
| AArch64 / RISC-V | V0–V4, plus V5 and V6 via qemu-user                                                                                  |

### 13.3 Tamper and minimality

**Tamper gate.** After every apply:

- protected files keep their hashes: `tests/`, `contracts.yaml`, `project.yaml`, the Makefile;
- `gen/` regenerated from the registry is byte-identical;
- no file appears outside the write scope.

**Minimality gate** (edit mode). The diff touches only declared symbol spans (from the repo map) or declared new files.

### 13.4 Sandbox policy

**Assemblers and linkers**, in `bart-tc`:

- `--network none`, non-root, read-only root filesystem, tmpfs `/tmp`;
- only the runs directory is mounted;
- `%include`, `incbin` and fasm `file` paths are pre-scanned and fenced to the staged project, so a request like `incbin "~/.ssh/id_rsa"` cannot leak host files;
- NASM `--limit-*` options and fasm pass limits;
- timeouts and output caps.

**Generated binaries** run in a fresh `bart-run` container per test batch:

```
--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534
--memory 256m --memory-swap 256m --pids-limit 64 --cpus 1 --ulimit nofile=64
--ulimit fsize=16777216 --tmpfs /tmp:size=16m -v <attempt>:/work:ro
```

plus `timeout -s KILL`. gVisor `runsc` is an optional extra layer.

**Emulator child:** syscall allow-list, instruction cap, time cap, and a separate process.

**Never:**

- generated code on the Windows host, or in a bare WSL shell. WSLInterop is enabled, so a Linux binary could launch Windows `.exe` files and write to `/mnt/c`;
- mounting the Docker socket;
- secrets inside containers;
- `shell=True`;
- LLM access to a shell. LLMs only produce text; tools are typed functions called by engine code.

## 14. Knowledge layer

**Sources.**

- `knowledge/sources.yaml` lists each source: id, URL or path, version, license, parser, tags, include/exclude lists, sha256.
- `asm_doc/` holds the local manuals and is tracked in git (owner decision, 2026-10-13; check the licenses in `docs/knowledge-sources.md` before publishing the repo):
  - NASM 3.02 `nasmdoc.txt` (BSD-2);
  - fasm, fasmg and win32 headers HTML;
  - binutils `as.htm`, `LD.htm`, `binutils.htm` (GFDL);
  - the MASM PDF.
- MASM content is better ingested from the MicrosoftDocs `cpp-docs` Markdown (CC-BY-4.0): one file per directive, and it avoids PyMuPDF, which is AGPL.

**Priority additions:**

- **P0:**
  - hand-written dialect rule cards;
  - the SysV psABI summary (summarize, don't mirror) and the Microsoft x64 calling convention;
  - the Linux `syscall_64.tbl`;
  - NASM Appendix F instruction forms;
  - instruction tables from Opcodes x86_64.xml, or asmjit `isa_x86.json` (zlib license).
- **P1:**
  - the FASM INCLUDE and EXAMPLES packages;
  - win32metadata for the Windows API (MIT);
  - felixcloutier.com, as deep links only.
- **P2:** uops.info data and Agner Fog's manuals, as links only (their licenses don't allow mirroring).

**`var/kb/facts.sqlite`** (exact lookup, used first). Tables:

- `insn_forms(arch, assembler, mnemonic, operands, cpu_flags)`;
- `insn_ref(arch, mnemonic, intel, att, operands_rw, implicit_in, implicit_out, flags_rw, isa_ext, summary, url)`;
- `directives(dialect, name, aliases, synopsis, chunk_ids)`. Covers 118 GAS pseudo-ops, 180 MASM directives, and the NASM and fasm directive headings;
- `diagnostics(dialect, code, message_regex, chunk_id)`;
- `syscalls(os, abi, nr, name, args_json, arg_regs)`;
- `winapi(dll, name, params_json, ret)` (P1);
- `abi_conventions(abi, int_args, fp_args, ret, callee_saved, volatile, stack_align, shadow, red_zone)`.

Keys come from regex extraction over the plan, the code and the errors. Python does the retrieval, so models never need to call tools.

**Docs index** (MVP: `var/kb/docs_fts.sqlite`, SQLite FTS5 BM25):

- **Chunking:** by document structure, at most 480 tokens per chunk. Code blocks and tables stay whole.
- **Breadcrumb header** on every chunk, e.g. `[NASM 3.02 › 5 Preprocessor › 5.3 Multi-Line Macros]`.
- **Tokenizer:** `unicode61 tokenchars '%.@$_#'`, so `%macro` and `.globl` stay single tokens. A second column holds the bare forms.
- **Corpus:**
  - NASM chapters 1–14 and Appendices A–B. Appendix C, the version history, is dropped; Appendix F goes to SQLite instead.
  - From `as.htm`: Invoking, Syntax, Sections, Symbols, Pseudo-Ops, i386, and later AArch64 and RISC-V.
  - From `LD.htm`: the Scripts section.
- **Quality bar:** a golden set of at least 60 queries, measured by recall@5 and MRR.

**Qdrant hybrid search** (Phase 3, only if the retrieval eval shows a gain):

- dense vectors: nomic-embed-text v1.5 (768 dimensions, with `search_document:` / `search_query:` prefixes), from LM Studio or FastEmbed — the two providers' vectors are not interchangeable;
- sparse vectors: asm-aware BM25 computed client-side (mmh3 hashes, IDF modifier);
- fusion: RRF;
- filters: dialect, arch, OS, status;
- collections `bart_docs_vN`, `bart_lessons_vN` with aliases.

Deployment: the project's own `barthelona-qdrant` from `docker/qdrant/compose.yaml` (D-034), storage in a named volume; Qdrant documents data loss on Windows bind mounts (https://qdrant.tech/documentation/common-errors/). The product uses `qdrant-client`. The Qdrant MCP server is only a development aid for Claude Code.

**Rule cards.** `knowledge/rulecards/<dialect>-<target>.md`, about 400 tokens each, always injected. They cover:

- the section and entry boilerplate;
- the import/export syntax;
- the calling convention and alignment rules;
- syscall conventions;
- common pitfalls.

Examples of pitfalls: NASM `default rel` and `wrt ..plt`; GAS `.intel_syntax noprefix` operand order; `.note.GNU-stack`.

## 15. Memory

### 15.1 Contract registry and code generation

| Dialect           | Export                                                           | Import          | Struct / const          |
| ----------------- | ---------------------------------------------------------------- | --------------- | ----------------------- |
| NASM              | `global f`                                                       | `extern f`      | `struc/endstruc`, `equ` |
| GAS               | `.globl f` + `.type f,@function`                                 | implicit        | `.equ` offsets          |
| FASM object (P4)  | `public f`                                                       | `extrn f`       | `struct` macro, `=`     |
| FASM PE/flat (P4) | modules are `include`d; the header holds consts and structs only |                 |                         |
| MASM-family (P4)  | `PUBLIC f`                                                       | `EXTERN f:PROC` | `STRUCT`, `EQU`         |

Rules:

- Each module gets `gen/<module>.inc` containing its exports and only its own imports. A module never declares `extern` for a symbol it defines.
- Generated files carry a hash header (`<comment> GENERATED ... barthelona-gen v1 body-sha256=<hex>`, the hash covers the body) and are committed, so the project builds without barthelona. The tamper gate regenerates `gen/` from the registry and flags every missing, edited or extra file (`tamper.missing`, `tamper.edited`, `tamper.extra`); `barthelona verify --contracts` runs it first and stops on failure.
- `gen/contracts.h` holds the C prototypes of global functions (register types `u8`..`u64`, `i8`..`i64`, `usize`, `char`, pointers to them) and consts and struct offsets as enum constants. Each `c_harness` test at V5 gets `gen/harness/<id>.c`: it calls the function with the integer inputs in declared order and exits 1 if the first output differs from `expect.ret`.
- When a contract hash changes, dependent modules are marked stale.

### 15.2 Lessons (evidence-gated experience log)

SQLite (`app.sqlite.lessons`) is the source of truth.

**Creation.** `retro` proposes a lesson only when a failure turned into a pass within the sprint, with the fixing diff attached as evidence.

**Dedupe.** An exact `error_sig` match in the same scope merges into the existing lesson (`alpha += 1`). Rejected lessons are kept so they are not proposed again.

**Promotion:**

- `candidate → active`: automatically, when the lesson's regression check passes in the sandbox.
- `active → approved`: by a human, in the inbox.
- `deprecated`: when the toolchain version changes and the check fails, or when confidence drops below 0.35 after at least 5 uses.

**Scoring and use:**

- Score = `alpha / (alpha + beta)` × decay (90-day half-life; approved lessons do not decay) × scope bonus.
- Agents must cite the ids of lessons they use. A cited lesson in a step that passes gets `alpha++`; if the same error recurs after injection, `beta++`.

**Injection:**

- On a failure: exact lookup by `error_sig` first.
- At the start of a task: the top 3 lessons for the task's terms, within scope.
- Format: `L-17 [nasm/elf64] Use "default rel" for RIP-relative data (conf .86)`.

**Phasing.** Storage arrives in P2. Injection is enabled only after the benchmark shows a gain. Reflexion-style gains depend on external feedback (https://arxiv.org/abs/2303.11366).

### 15.3 Repo map (edit mode)

- Built as described in §6.2 and stored in `.barthelona/repomap.json`.
- Rendered per symbol as: signature line, contract summary, first comment line.
- Re-indexed incrementally by content hash after every increment.
- There is no vector index over project code.

## 16. LLM routing, structured output, context

### 16.1 Gateway

`llm/gateway.py` is a `ModelGateway` protocol. Each backend uses its provider's official SDK:

| Backend                  | SDK                                            | Serves                                                                     |
| ------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------- |
| `OpenAIChatBackend`      | `openai` 3.x, Chat Completions with `base_url` | LM Studio, Ollama, llama.cpp, DeepSeek, QwenCloud/Qwen3                    |
| `OpenAIResponsesBackend` | `openai` 3.x, Responses API                    | OpenAI (GPT-6 models need it for tool calls with reasoning)                |
| `AnthropicBackend`       | `anthropic` 1.x                                | Claude                                                                     |
| `GeminiBackend`          | `google-genai` 2.x                             | Gemini (the OpenAI-compatible endpoint's schema enforcement is unverified) |
| `FakeGateway`            | none, scripted                                 | tests                                                                      |
| cassette backend         | none                                           | replay                                                                     |

LiteLLM is excluded: PyPI releases 1.82.7 and 1.82.8 were malicious in March 2026 (https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/).

The gateway provides:

- one semaphore per endpoint (local: 1 in flight);
- a **model-affinity scheduler** that groups queued calls by model, because reloading a model on this machine costs seconds to minutes and wipes the prefix cache;
- a **role router** that walks the role's chain for the run's profile (§16.2), skipping disabled providers, missing keys and open circuits (§16.6);
- a **cost ledger**: every call's cost comes from the API's reported usage times the catalog prices, with optional caps enforced by reserve-then-settle (§16.6);
- an `LLMCallRecord` for every call, including which model actually served the role and why (fallback reason);
- normalization of provider differences: reasoning parameters (`output_config.effort`, `reasoning.effort`, `thinking_level`, DeepSeek `thinking` + `reasoning_effort`), structured output (json_schema vs DeepSeek `json_object` + Pydantic validation), refusals (`stop_reason: refusal`, OpenAI `refusal` items, Gemini `finish_reason: SAFETY`, DeepSeek `content_filter`), and echoing of reasoning items or `reasoning_content` in multi-turn tool use;
- stripping of `<think>` blocks from local model output.
- **endpoints (D-047):** a provider lists `endpoints[]` (`base_url`, `host_label`, `max_concurrency`); a model is usable on an endpoint only if it is loaded there; semaphores, circuit breakers and the affinity scheduler work per (endpoint, model), and `LLMCallRecord` records the endpoint.

### 16.2 Models, roles and profiles (`config/models.yaml`)

The catalog is a committed YAML file with no secrets. It has six parts:

- `providers`: kind, base URL, `api_key_env`, concurrency, structured-output mode;
- `models`: provider model id, price class (`price_class`), context, max output, reasoning controls, `price` (input, cached input, output per 1M tokens) and `pricing_checked`;
- `profiles`: an ordered role → model chain per profile;
- `default_profile`;
- `budget` (all optional);
- `resilience` parameters.

Cloud models in the catalog (Anthropic/OpenAI/Google/DeepSeek verified 2026-10-13; QwenCloud/Qwen approximate, verify in QwenCloud console; prices in USD per 1M tokens, input / cached input / output):

Price classes within a provider (`price_class` in the catalog; not to be confused with node roles):

| Provider          | Frontier                                     | Flagship                                                    | Mid                                                                               | Cheap                                                                      |
| ----------------- | -------------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Anthropic         | `claude-fable-5-1` 10 / 0.25 / 50 (disabled) | `claude-opus-5-5` 4 / 0.20 / 20                             | `claude-sonnet-5-5` 2 / 0.10 / 10                                                 | `claude-haiku-5-5` 0.10 / 0.01 / 0.50 (prompts > 100K: 0.50 / 0.05 / 2.50) |
| OpenAI            | `gpt-6-astra` 10 / 1 / 50                    | —                                                           | `gpt-6.1-sol` 2 / 0.10 / 10; `gpt-6-sol` 2 / 0.20 / 10                            | `gpt-6-luna` 0.10 / 0.01 / 0.50                                            |
| Google            | —                                            | `gemini-3.1-pro-preview` 2 / 0.20 / 12 (preview only)       | `gemini-3.8-flash`, `gemini-3.6-flash` 0.75 / 0.075 / 3.75 (double on 2027-01-01) | `gemini-3.5-flash-lite` 0.30 / 0.03 / 2.50                                 |
| DeepSeek          | —                                            | `deepseek-v4-pro` 1.32 / 0.044 / 3.96 (peak; off-peak −50%) | `deepseek-flash` 0.30 / 0.006 / 1.20 (peak; off-peak −50%)                        | `deepseek-flash` with thinking disabled                                    |
| QwenCloud (Qwen3) | —                                            | `qwen3-235b-a22b` ~0.30 / — / ~3.00 (thinking)              | `qwen3-30b-a3b` ~0.10 / — / ~0.44                                                 | `qwen-turbo` ~0.05 / — / ~0.20 (disabled)                                  |

Long-context tiers (OpenAI above 272K input, Gemini Pro above 200K, Haiku above 100K), cache-write prices and DeepSeek's off-peak schedule are machine-readable `price` fields, so the ledger and budget reservations use the right rate.

Excluded from every chain: retiring or legacy models (`o3-pro`, which retires on 2026-12-11; o-series; gpt-4.x; Gemini 2.5, which is restricted to previous users; DeepSeek legacy aliases).

Profiles. Every chain ends in `local_main`. The default is `hybrid`. Chain entries carry per-role reasoning settings (for example `{model: claude-opus-5-5, effort: high}`), because the gateway always sets effort/thinking explicitly.

| Role                        | local-only | hybrid                                                                                                             | cloud                                                                                                                      |
| --------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| main                        | local      | local                                                                                                              | Sonnet 5.5 → Qwen3-30B (no-think) → GPT-6.1 Sol → Gemini 3.8 Flash → DeepSeek Flash → local                                |
| planner                     | local      | Opus 5.5 (high) → Qwen3-235B (think) → GPT-6.1 Sol (high) → Gemini 3.1 Pro (high) → DeepSeek V4 Pro (high) → local | same as hybrid                                                                                                             |
| worker                      | local      | local                                                                                                              | Sonnet 5.5 → Qwen3-30B (no-think) → GPT-6.1 Sol → GPT-6 Sol → Gemini 3.8 Flash → Gemini 3.6 Flash → DeepSeek Flash → local |
| cheap                       | local      | local                                                                                                              | Haiku 5.5 (low) → GPT-6 Luna (none) → Gemini 3.5 Flash-Lite (minimal) → DeepSeek Flash (thinking off) → local              |
| escalation (flagship-first) | local      | Opus 5.5 (high) → Qwen3-235B (think) → GPT-6.1 Sol (xhigh) → Gemini 3.1 Pro (high) → DeepSeek V4 Pro (max) → local | Opus 5.5 (xhigh) → Qwen3-235B (think) → GPT-6 Astra (high) → Gemini 3.1 Pro (high) → DeepSeek V4 Pro (max) → local         |

The owner reorders chains freely; the order is a preference, not a dependency. The `cheap` role is reserved: no MVP node uses it yet.

**One local model stays loaded and serves every local role.** It is a mixture-of-experts model with about 3B active parameters, chosen by the Phase 0 bake-off. Candidates:

| Model                               | Status        | Notes                                                                      |
| ----------------------------------- | ------------- | -------------------------------------------------------------------------- |
| Qwen3-Coder-30B-A3B                 | not installed | no thinking mode; about 17–19 GB at Q4                                     |
| Qwen3.6-35B-A3B                     | not installed | thinking on by default, so turn it off for coding calls; about 20 GB at Q4 |
| gpt-oss-20b                         | not installed | fits in 16 GB                                                              |
| liquid/lfm2-24b-a2b                 | installed     |                                                                            |
| mistralai/ministral-3-14b-reasoning | installed     | dense, so slower                                                           |

Not candidates for the main model:

- prism-ml/bonsai-27b: a Q1_0 quantization, so expect weak precision;
- google/gemma-4-e2b: too small for code, but usable for classification only if RAM allows a second resident model.

**Memory budget.**

- Measured: 32 GB RAM; WSL takes about 15 GB by default.
- Estimated:
  - Qwen3-Coder-30B-A3B's KV cache is about 96 KiB per token in fp16 (48 layers × 4 KV heads × 128 dims × 2 × 2 bytes);
  - that is about 3 GiB at 32K tokens, or about 1.5 GiB with a q8_0 KV cache;
  - weights plus KV come to about 21 GB.
- Therefore:
  - cap WSL at about 8 GB in `.wslconfig` (a user action);
  - default context 16K, maximum 32K;
  - q8_0 KV cache;
  - Qdrant stays off in the MVP.

**Expected speed.** About 8 tok/s decode, an anecdotal figure for this CPU generation. That means minutes per module, which is why the design uses:

- hunks instead of whole-file rewrites;
- files of at most 250 lines;
- stable prompt prefixes;
- the `cloud` profile, which moves the worker role to cloud models;
- an overnight queue.

### 16.3 Output protocols

- **JSON only for small artifacts:** spec, contracts, plans, verdicts, localization.
  - Local models: LM Studio `response_format: {type: "json_schema"}`, enforced by grammar sampling for GGUF models. LM Studio's docs warn that models under about 7B may struggle (https://lmstudio.ai/docs/developer/openai-compat/structured-output).
  - Cloud, per provider (`structured_output` in `config/models.yaml`): Anthropic `output_config.format` / `client.messages.parse()` and `strict: true` tools; OpenAI Responses `text.format` `json_schema` with `strict: true`; Gemini `response_mime_type: application/json` + `response_json_schema`; DeepSeek `response_format: json_object` only (the prompt must mention JSON), so its output is always validated and repaired.
  - Then Pydantic validation, then semantic validators, then at most 2 repair attempts that feed back up to 10 errors, then the next tier or a deterministic fallback.
- **Code never goes inside JSON.** Small models mangle escaped backslashes and quotes. Envelopes:
  - whole files: `=== FILE: src/str.asm ===` … `=== END ===`;
  - edits: `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` blocks, where each SEARCH must match exactly once;
  - symbol edits: `=== SYMBOL: src/str.asm :: str_len ===`.
- **Envelope parser rules:**
  - strict;
  - rejects paths outside the task's write scope, absolute paths and `..`;
  - every parse failure counts as a repair attempt;
  - fuzzed with Hypothesis.
- **Decoding:**
  - sampling parameters go to **local models only**: temperature 0–0.2, and up to 0.7 for local candidate sampling. Cloud models reject or ignore them (Claude 5.x returns 400; GPT-6 returns 400 at any effort except `none`; Gemini 3.x and DeepSeek thinking mode ignore or reject them), so cloud diversity comes from prompt variants;
  - each role uses one tool-free completion; MVP roles make no tool-calling loops.

### 16.4 Context assembly

Blocks are ordered from stable to volatile, so llama.cpp/LM Studio can reuse the cached prefix and a cloud cache breakpoint can sit after block 3 (D-039):

1. role and output format;
2. dialect rule card;
3. project card: target and ABI row;
4. contracts: the task's own plus direct callees;
5. exact facts;
6. lessons;
7. doc chunks;
8. code: the target region or file, and the repo map;
9. task, error and diagnostics.

| Role (16K profile) | Rule card | Contracts | Facts     | Docs | Code        | Task / errors | Output reserve |
| ------------------ | --------- | --------- | --------- | ---- | ----------- | ------------- | -------------- |
| spec / backlog     | 0.4K      | —         | 0.5K      | —    | —           | 2K            | 3K             |
| architect          | 0.5K      | 2K        | 1K        | 0.5K | repo map 2K | 1.5K          | 4K             |
| coder              | 0.5K      | 1.5K      | 1K        | 1.5K | `.inc` 0.3K | 0.5K          | 3K             |
| fixer              | 0.5K      | 0.5K      | 1K        | 1K   | file ≤3.5K  | 1K            | 1.5K           |
| reviewer           | 0.5K      | 0.5K      | lint 0.5K | —    | diff ≤3K    | 1K            | 0.8K           |

- **Never dropped:** role, rule card, the task's own contract, task and error.
- **Drop order when over budget:** lowest-scored doc chunks, then lessons, then repo-map depth, then callee contracts.
- **Cloud input cap:** the 16K table above is the local profile. For a cloud model that has a `long_context` price tier, the assembler caps the input of every call at `long_context.above_input_tokens` (Haiku 5.5: 100K, where input jumps from $0.10 to $0.50 per million tokens). Models without a tier (Opus 5.5, Sonnet 5.5) are not capped by this rule. A role can opt in to the higher tier; the opt-in key is defined together with the assembler (roadmap F-33).
- **Token counting:** the model's tokenizer where available, otherwise characters / 3.5 with a 15% margin.
- **Hidden tests never appear in prompts.**
- **Stable-prefix constraint (D-039):** blocks 1–3 must be byte-for-byte identical across all calls that share the same dialect, arch and policy version within a sprint run, so the provider can reuse the KV cache. The context assembler computes a `stable_prefix_hash` and raises an error if it changes mid-run. Block 3 is at most 25% of the context window; the assembler raises a hard error rather than silently truncating.
- **Semantic response caching is not used** (D-039). Each coding call is unique per code state. A false cache hit would corrupt a workspace without detection.
- **Provider prefix-cache marker:** for Anthropic, `cache_control: {"type": "ephemeral"}` is placed on the last block of the stable prefix (block 3). For LM Studio/vLLM, no marker is needed; the provider's automatic prefix caching fires when the prefix matches. The gateway logs `cache_hit` and `cache_tokens_saved` per call (D-024).

### 16.5 Claude specifics (verified 2026-10)

- **Prices** per million input/output tokens; all have a 1M-token context:

  | Model               | Price                           |
  | ------------------- | ------------------------------- |
  | `claude-sonnet-5-5` | $2 / $10                        |
  | `claude-opus-5-5`   | $4 / $20                        |
  | `claude-haiku-5-5`  | $0.10 / $0.50                   |
  | `claude-fable-5-1`  | $10 / $50 (not used by default) |

- **Opus 5.5:**
  - thinking cannot be disabled;
  - effort defaults to `medium`, so always set `output_config.effort` explicitly;
  - sampling parameters return a 400 (Sonnet 5.5 and Haiku 5.5 also reject non-default values), so the gateway never sends them to Claude (§16.3).
- **Forced `tool_choice` (`any`/`tool`)** returns a 400 on Opus 5.5, Sonnet 5.5 and Fable 5.1. Use structured outputs instead.
- **Refusals.** Handle `stop_reason: "refusal"` and its `stop_details.category`. Low-level assembly can trip the `cyber` classifier. Policy:
  - record the refusal;
  - send the server-side `fallbacks: "default"` parameter (beta `server-side-fallback-2026-07-01`) on Opus 5.5 and Sonnet 5.5;
  - if it still refuses, move to the next model in the role's chain (another provider), and notify the user at G5 only when the chain is exhausted.
- **Errors:**
  - 402 `billing_error`, or 400 "credit balance is too low": terminal for this provider;
  - 429 with `enforced_spend_limit_reached`: terminal until the limit resets;
  - 429 `rate_limit_error`: transient; honour `retry-after`;
  - 529 `overloaded_error`, 500, 504: transient.
  - The SDK retries 408/409/429/5xx twice by default. The gateway sets `max_retries=0` and applies its own policy, so retries are not multiplied.
- **Prompt caching:**
  - the minimum cacheable prefix depends on the model: 512 tokens for Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.1; 1024–4096 tokens for older models;
  - verify that `usage.cache_read_input_tokens` is greater than 0;
  - cache reads cost 0.05x the base input price on Opus 5.5 ($0.20 per million tokens) and Sonnet 5.5 ($0.10), and 0.1x on Haiku 5.5 ($0.01) (https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-10-17);
  - a 5-minute write costs 1.25x and a 1-hour write 2x the base input price, and every cache hit refreshes the 5-minute lifetime at no cost: use 5 minutes for tight worker loops and 1 hour only where calls are more than 5 minutes apart (planner roles).
- **Batch API:** 50% off. Use it for benchmark and Policy Lab runs.
- **API keys** come only from environment variables. They never appear in logs or in Streamlit session state.

### 16.6 Provider resilience and optional budgets

Cloud providers are treated as unreliable accelerators. A provider can throttle, go down, refuse, or run out of credit at any moment; each case has a defined reaction, and none of them crashes a run.

**Error classes.** Every backend maps provider errors into four classes:

| Class                     | Examples (verified 2026-10-13)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Reaction                                                                                                                                                                                                                      |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transient                 | 429 rate limit; Anthropic 529 overloaded; 500/502/503/504; timeouts and connection resets; DeepSeek `finish_reason: insufficient_system_resource`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Retry with exponential backoff and full jitter; `Retry-After` is the minimum wait. After `max_attempts`, count a failure toward the transient circuit and use the next model in the chain.                                    |
| Terminal for the provider | No credit: Anthropic 402 `billing_error` or 400 "credit balance is too low"; DeepSeek 402 Insufficient Balance; Gemini 402 `payment_required`; OpenAI 429 `credit_balance_exhausted` / `insufficient_quota`. Spend and usage limits: Anthropic 429 `enforced_spend_limit_reached` and 400 "You have reached your specified API usage limits"; OpenAI 429 `*_spend_limit_exceeded` / usage-limit codes; Gemini 429 quota exceeded and 400 `FAILED_PRECONDITION` (billing disabled). Bad keys: 401/403. Classification matches the error type, code or message substring, never the HTTP status alone, because several terminal conditions arrive as 400 or 429. | Open the provider's terminal circuit (cooldown 30 min, then one probe), emit a UI event (e.g. "anthropic: billing_error → switched to openai"), and continue with the next model in the chain. Never retry these immediately. |
| Model-level               | 404 model not found; 400 context too long; a model-specific 400 (unsupported parameter)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Mark the model unusable for the run, log it, and use the next model. A context overflow first triggers context shrinking (§16.4).                                                                                             |
| Output-level              | Invalid JSON or schema, empty or truncated output, refusal                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | At most 2 repair attempts with the validation errors; refusals use server-side fallbacks where available. Then the next model.                                                                                                |

**Circuit breakers** are kept per provider and per model:

- Transient circuit: opens after 3 failures in 120 s and half-opens after 60 s.
- Terminal circuit: half-opens after 30 min with a single cheap probe.
- State is shown on the Toolchains & models page and survives worker restarts (`app.sqlite`).

**Transport.**

- Each provider has its own `timeout_s` (600–1800 s). Calls with `max_tokens` above 16K, or with long reasoning, are always streamed.
- SDK-internal retries are disabled so attempts are not multiplied: `max_retries=0` for `openai` and `anthropic`, `HttpRetryOptions(attempts=1)` for `google-genai`.

**Degradation, never death.**

- Every role chain ends in `local_main`.
- When the chain falls back to a weaker tier, the planner shrinks the unit of work and tightens loops (§9.5).
- If even the local model is unavailable (LM Studio down), the run drains to a resumable checkpoint with `StopReason.no_model_available`. It resumes when a model is reachable again, for example after LM Studio restarts, a key is added, or a provider is topped up.
- Because acceptance is decided by the verification ladder, a degraded or flaky model can waste attempts but cannot corrupt the project (Principle 1).

**Optional budgets with a hard guarantee.** All dollar caps are optional; with no cap, every call is still metered (per call, sprint, run and provider) and shown in the UI. When a cap is set, the gateway enforces it by reserve-then-settle:

1. Before a call, reserve its worst-case cost at the highest price tier the request can reach (long-context tier, peak rate, cache writes): prompt tokens × input price + `max_tokens` × output price.
2. If the reservation does not fit the remaining cap, the call is not made. The `budget.on_exhausted` policy applies: `ask` (G5, the default), `fallback_local`, or `stop`.
3. After the call, settle the actual cost from the API's usage, and release the unused part of the reservation.
4. A warning event is emitted at `warn_at` (default 80%) of any cap.

Caps exist per run, per month, and per provider. Spend history is kept in `app.sqlite` (`llm_calls`).

**Health probes.**

- At worker start, and before a run that allows cloud use, the gateway checks each enabled provider: key present, then a models listing or a minimal call.
- Results and cooldowns feed the circuit state.
- Local endpoints are probed through LM Studio's `/api/v1/models` (`loaded_instances`) and Ollama's `/api/ps`.

## 17. UI and process model

**Processes.**

- `scripts/run.ps1` starts the worker (`python -m barthelona worker`) and `streamlit run src/barthelona/ui/app.py`.
- The UI writes only:
  - `runs` (queued);
  - `commands`: `resume{gate_id, decision, edits}`, `cancel`, `retry_task`, `extend_budget`;
  - user edits to approval payloads.
- The worker claims runs and streams the graph with `stream_mode=["updates","custom"], version="v2", durability="sync"`. It appends events in batches about every 250 ms (events that define resumable truth are flushed first, D-044), and records interrupts in the `gates` table.
- **Gates.** On a `resume` command the worker calls `graph.astream(Command(resume=…))`.
- **Cancel.** `request_drain()` leaves a resumable checkpoint.
- **After a crash,** the worker streams `None` on the same `thread_id`.
- **Streamlit rules:**
  - Streamlit threads cannot host the engine (https://docs.streamlit.io/develop/concepts/design/multithreading), so the UI never starts threads;
  - live pages use `@st.fragment(run_every=1)` and read only `seq > last_seq`;
  - `st.cache_resource` is used only for a read-only SQLite handle (`check_same_thread=False`, WAL).

**Pages** (`st.navigation` with `st.Page`; MVP pages marked \*):

| Page                  | Contents                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| New request\*         | Mode, dialect, target preset (unsupported presets disabled with the reason), workspace or import path, description (RU/UK/EN), profile, cloud consent and allowed providers, optional dollar budget (empty = uncapped but metered), time and token limits (empty = profile default; never unlimited), composition level, autopilot, collect training data (defaults to the setting, §19). |
| Approvals\*           | Gate inbox. Editable spec, test and contract tables; contract-delta view; diff view for G4.                                                                                                                                                                                                                                                                                               |
| Sprint board\*        | Backlog, sprint and done columns. The current topology rendered with `st.graphviz_chart` from DOT, showing the chosen template, insertions, knobs and why. A story × level ladder matrix with clickable diagnostics.                                                                                                                                                                      |
| Live run\*            | Current phase and node, attempts, tok/s, ETA, spend per provider (and vs. the cap, if one is set), which model is actually serving each role, event log (including fallbacks such as "anthropic: billing_error → deepseek"), cancel button.                                                                                                                                               |
| Review\*              | Diff, ladder evidence, sandboxed program output, run-with-input (sandboxed).                                                                                                                                                                                                                                                                                                              |
| Toolchains & models\* | Probe results, image digests, LM Studio models with loaded state and max context, profiles, latency test. Provider health per cloud provider (key present, last probe, circuit state green/yellow/red, cooldown), the model catalog with prices and `pricing_checked` dates, and spending history.                                                                                        |
| Runs                  | History, replay, cost.                                                                                                                                                                                                                                                                                                                                                                    |
| Knowledge             | Ingest status, search playground.                                                                                                                                                                                                                                                                                                                                                         |
| Retro & policy (P2+)  | Retro reports, overlay log with revert, lessons inbox (P3), policy patches, Lab results, activate and rollback (G6).                                                                                                                                                                                                                                                                      |
| Bench                 | P1 via the CLI; the page comes later.                                                                                                                                                                                                                                                                                                                                                     |

UI language is English. Input in Russian or Ukrainian is accepted; the normalized English spec is shown back to the user for approval.

## 18. Persistence and workspace layout

**`var/` (gitignored):**

- `app.sqlite` (WAL). Tables: `runs`, `commands`, `events`, `gates`, `llm_calls`, `exec_log`, `lessons`, `lesson_uses`, `overlay_changes`, `policy_pointer`, `metrics`, `bench_results`.
  - Schema versions are tracked with `PRAGMA user_version`; migrations are append-only (`persistence/migrations.py`). Migration 1 creates the first five tables as STRICT tables; each later table arrives with its feature as a new migration.
  - Each row stores the domain document as JSON (`Run`, `RunCommand`, `RunEvent`, `GateRequest`/`GateDecision`, `LLMCallRecord`) next to a few indexed columns, and every read validates it back into its model.
  - Writes run in `BEGIN IMMEDIATE` transactions. Event numbers per run are contiguous from 0, commands are claimed exactly once, and a gate is resolved once with one of its offered options. Event payloads, gate payloads and gate-decision edits over 16 KiB are refused; bulky data goes under `runs/<run_id>/` and is referenced by `payload_ref`.
- `checkpoints.sqlite`: LangGraph `AsyncSqliteSaver`.
- `worker.lock`.
- `runs/<run_id>/`:
  - `events.jsonl`;
  - `llm/<seq>.json` with prompt, response, params and model hash;
  - `exec/<seq>.{argv,out,err}`;
  - `report.md`.
- `kb/`: `facts.sqlite`, `docs_fts.sqlite`, and `emb_cache.sqlite` (P3).
- `training/` (only when training-data collection is on, §19): `samples.jsonl` and `texts/<aa>/<sha256>.txt`.
- `policies/vN/` (runtime-created versions) and `bench/<suite>/<timestamp>/`.

**A project workspace** is its own git repository at `<workspaces>/<slug>/`. The default root is `<repo>/workspaces/` (gitignored), configurable with `BARTHELONA_WORKSPACES`.

```
project.yaml         ProjectSpec + TargetProfile + build recipe
contracts.yaml       registry (source of truth)
src/*.asm | *.s      LLM-written, only within each task's write scope
gen/                 GENERATED, hash header, committed: *.inc, stubs/, contracts.h, harness/*.c, fixtures/
tests/               acceptance.yaml, unit/*.yaml, reference/*.py, characterization/ (locked, hashed)
Makefile, .gitattributes (eol=lf), README.md   generated
.github/             GENERATED once (D-048): workflows/ci.yml, workflows/release.yml, dependabot.yml
build/               ignored
.barthelona/         backlog.yaml, sprints/NN/{plan,topology,review,retro}.json, repomap.json,
                     policy_overlay.yaml, inferred_contracts.yaml, baseline/
```

Git rules:

- One branch per run: `bart/<run_id>`.
- One commit per green task and a tag per increment.
- Failed attempts stay only in `var/runs`.

## 19. Observability

The baseline is the product's own event log, which also feeds the UI.

**Metrics:**

- velocity;
- first-try pass rate;
- attempts per task and escalations;
- tokens, cost and cache hits;
- schema failures and repairs;
- tok/s and time per node;
- tamper attempts.

**Tracing and replay:**

- LangGraph `get_state_history` gives time travel.
- `barthelona replay <run_id>` re-runs a run from LLM cassettes, so the deterministic parts are byte-reproducible.
- With `BARTHELONA_OTEL=1`, OpenTelemetry spans are emitted through `openinference-instrumentation-langchain` to an Arize Phoenix instance:
  - Phoenix runs separately (Docker in WSL or a separate env) under the Elastic-2.0 license;
  - it is never a dependency of the main environment.

Langfuse and LangSmith are excluded: self-hosting Langfuse is too heavy for this machine, and LangSmith is SaaS.

**Training data (opt-in, D-036).** Runs can collect a dataset for training an assembly-programming model later; fine-tuning itself stays out of scope (§1).

- **Setting:** `BARTHELONA_TRAINING_DATA_ENABLED` (default off) and `BARTHELONA_TRAINING_DATA_DIRECTORY` (default `var/training`), read from the process environment by `training.TrainingDataSettings`. The New request page offers a "Collect training data" checkbox that defaults to the setting; the choice is pinned as `Run.collect_training_data`. `python -m barthelona training status` prints the setting and the sample count per verdict.
- **What:** one `TrainingSample` (§4) per code-producing model attempt, recorded after the tamper gate and the ladder have judged it, so the label comes from the oracles. Failed attempts are kept: a rejected attempt and the accepted retry that names it in `improves_on_seq` form a preference pair.
- **Where:** local files only, never uploaded: `samples.jsonl` (metadata, one sample per line) and content-addressed `texts/<aa>/<sha256>.txt` for prompts and responses, so code stays out of JSON (invariant 5). Secrets are redacted before a text is written. The worker is the only writer.
- **Not collected:** holdout benchmark attempts (no `SampleSource` value exists for them, `source` is required, and the engine hook refuses runs on holdout tasks) and deterministic nodes.
- **Export** (Phase 1): `barthelona training export` writes trainer-ready files; by default it keeps only local-model samples, because provider terms may restrict training on cloud outputs.

## 20. Evaluation

- **Unit tests** (no LLM, no WSL):
  - diagnostic parsers against real captured tool output, per tool version;
  - generators against golden files, per dialect;
  - registry validators and the envelope parser (with fuzzing);
  - `error_sig`, budgets, the composer, and the topology validator (property tests);
  - path and CRLF utilities.
- **Oracle tests:** the ABI mutation corpus (§13.1).
- **Graph tests** with `FakeGateway` and `FakeExecutor`, scripted per (node, attempt):
  - happy path and fix loop;
  - stall jump and escalation order;
  - interrupt/resume and crash/resume;
  - budget stops;
  - tamper rejection;
  - refusal handling;
  - policy pinning.
- **Integration tests** (`-m wsl`): the real images running known-good and known-bad projects.
- **UI tests:** `streamlit.testing.v1.AppTest` for page logic.
- **Benchmark** (`bench/tasks/{dev,holdout}/<dialect>/<id>/` with `task.yaml`, an optional `seed/`, and `hidden/` tests):
  - **MVP set:** 12 create tasks and 8 edit tasks.
    - Create: strlen, atoi, itoa, memcpy, insertion sort, hexdump CLI, wc, bigint add, a multi-module tokenizer.
    - Edit: injected bugs (misaligned call, clobbered rbx, off-by-one, wrong syscall number, missing `default rel`) and small features.
  - **Phase 0 bake-off tasks (#113):** ten integer-in, integer-out functions (gcd, popcount, fib, factorial, rotl, max_u64, isqrt, is_prime, collatz_steps, sum_to_n) in `bench/tasks/dev/nasm/<id>/` with `task.yaml`, `contracts.yaml` and `hidden/tests.yaml` (V5 `c_harness` cases, never shown to a model). Memory and string tasks wait for the pointer cases of the V5 harness (roadmap F-56). Arms: `single` (no fix iterations) and `fix` (up to N iterations fed with the oracle output); both are bounded by attempts and tokens and stop with a `StopReason`. Arms are compared by task (paired bootstrap, several seeds), `bench/prompts/*.md.j2` hold the prompts.
  - **Growth:** to 60 tasks.
  - **Metrics:** solved within budget, first-try green, attempts, escalations, tokens, time, dollars, schema failures, tamper attempts.
  - **Baseline:** one prompt to the same model, which the agent must beat.
  - **When it runs:** every prompt, model or policy change. A regression beyond the threshold blocks the change.
  - The holdout set is never shown to any LLM during development.
- **Retrieval eval:** at least 60 queries, measured by recall@5 and MRR.

## 21. Safety and security

| Threat                                                  | Control                                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Generated binary escapes or damages the host            | Hardened ephemeral containers; emulator allow-lists; never run on Windows or in bare WSL                                        |
| Assembler-time file leak (`incbin`, `%include`, `file`) | Include fence, staged workdir, no secrets on the staging volume                                                                 |
| LLM writes outside its scope or weakens tests           | Envelope path fence, write scopes (validator rule T7), tamper gate, frozen and hashed tests, hidden tests                       |
| Prompt injection from imported repos, docs or web       | Treated as data inside delimited blocks; no tool access for local roles; web research only in P5, gated and stored at low trust |
| Runaway loops or cost                                   | Validator rules T5 and T8, caps, `recursion_limit`, node timeouts, dollar caps, drain                                           |
| Secret leakage                                          | Keys only in the environment; redacted from logs and events; never in Streamlit session state or containers                     |
| Supply chain                                            | Hash-locked requirements (`--require-hashes`); pinned image digests; no LiteLLM; AGPL PyMuPDF kept out of the product           |
| Cloud data egress                                       | Per-run consent; the profile is shown on every run; local-only profile available                                                |
| Training data leaks secrets or leaves the machine       | Off by default; local files only, never uploaded; secrets redacted before writing; holdout attempts never recorded (D-036)      |
| Self-modification abuse                                 | Immutable policy versions, invariants, holdout A/B, human activation at G6, rollback                                            |

## 22. Known uncertainties and spikes

- **Assembly quality of local models is unknown.** No per-dialect benchmark has been published. Our own bake-off decides.
- **8 tok/s is anecdotal.** The bake-off measures the real figure.
- **Resuming a compiled sprint subgraph** is the Phase 1 spike; the interpreter is the fallback.
- **Thinking switches:** how to turn thinking off through LM Studio differs per model and must be verified for each candidate.
- **FASM** emits no DWARF. Line mapping from its `-s` symbol dump needs a prototype in P4.
- **Unicorn and AVX:** 256-bit VEX instructions are unsupported, so that code is routed to V5.
- **NASM versions:** 3.01 in apt, docs for 3.02, 2.16.03 on conda-forge. Versions are recorded per build.
- **Qdrant:**
  - local-mode support for RRF is unverified;
  - server 1.19.0 was measured; pin the client to minor version 1.19.
- **LM Studio prefix-cache reuse** is fragile across different system prompts.
- **OpenVINO Model Server** on the Arc iGPU is an untested later experiment.
- **Cloud refusal rate** for assembly work is unknown and is measured in the benchmark.
