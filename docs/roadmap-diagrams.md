# Roadmap diagrams: what Barthelona looks like when finished

Ten diagrams of the finished system, drawn from `docs/architecture.md` and the accepted-for-now ADRs. Use them to check a delivered phase against the plan: every box says whether it exists today, and the caption under each diagram names the phase that delivers it. The roadmap itself is `docs/roadmap.md`.

Status colours (as of 2026-10-17, from `main`; check `docs/roadmap.md` before relying on a box being built):

```mermaid
flowchart LR
    done["Exists on main"]:::done
    wip["In progress (Phase 0)"]:::wip
    planned["Planned"]:::planned
    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
```

Keep the diagrams current: when a box lands, change its class in the same PR. If a diagram and the architecture disagree, `docs/architecture.md` wins and the diagram is fixed.

| # | Diagram | Architecture section | Delivered in |
| --- | --- | --- | --- |
| 1 | System and processes | §3 | Phase 0 (spine), Phase 1 (UI, engine) |
| 2 | Package layering | §3, D-045 | Phase 0 onward |
| 3 | Run lifecycle: create and edit | §6 | Phase 1 (create), Phase 3 (edit of external projects) |
| 4 | Meta-agentic sprint loop | §7, §9 | Phase 1a (L0), 1b (L1), Phase 2 (L2) |
| 5 | Task pipeline and escalation ladder | §8, §9.2 | Phase 1 |
| 6 | Verification ladder and gates | §13, D-046 | Phase 0 (V0-V2, V5, V6), Phase 2 (V3, V4) |
| 7 | Execution, sandbox and crash consistency | §7, §13.4, D-043, D-044 | Phase 0 (executors), Phase 1 (crash spike) |
| 8 | Model gateway and role chains | §16, D-047 | Phase 0 (minimal), Phase 1b (all providers) |
| 9 | Data and workspace layout | §18 | Phase 0 (store), Phase 1 onward |
| 10 | Phases and what each one adds | `docs/roadmap.md` | all |

## 1. System and processes

Two Windows processes talk only through SQLite; everything that runs generated code lives in WSL Docker containers or the emulator child. Delivered: executors, store and toolchain probe in Phase 0; the UI, worker and gateway backends in Phase 1.

```mermaid
flowchart TB
    user(["Owner (browser)"])

    subgraph win["Windows host (conda env barthelona)"]
        ui["Streamlit UI<br/>queues runs, answers gates, shows events"]:::planned
        subgraph worker["Engine worker (one instance)"]
            engine["Outer run graph + sprint subgraphs<br/>LangGraph"]:::planned
            gateway["LLM gateway<br/>routing, ledger, breakers"]:::planned
            kb["Knowledge<br/>facts.sqlite + FTS5"]:::planned
            emu["Emulator child process<br/>Unicorn + Capstone (V3, V4)"]:::planned
            exec["Executors<br/>WslExecutor, FakeExecutor"]:::done
        end
        app[("var/app.sqlite (WAL)<br/>runs, commands, events, gates")]:::done
        ckpt[("var/checkpoints.sqlite<br/>LangGraph control position")]:::planned
        ws[("Workspaces<br/>one git repo per project")]:::wip
    end

    subgraph wsl["WSL2 Ubuntu"]
        agent["WSL agent<br/>JSON lines, path fence, allowlist"]:::done
        tc["bart-tc container<br/>nasm, as, ld, gcc, make, gdb<br/>no network"]:::wip
        run["bart-run container<br/>ephemeral sandbox per test batch"]:::wip
    end

    subgraph models["Model endpoints"]
        lm["LM Studio 127.0.0.1:1234<br/>local main model"]:::planned
        cloud["Anthropic / OpenAI / Gemini / DeepSeek / Qwen<br/>opt-in, per-run consent"]:::planned
    end

    user --> ui
    ui -- "writes runs, commands" --> app
    app -- "events, gates" --> ui
    engine <--> app
    engine <--> ckpt
    engine --> gateway
    engine --> kb
    engine --> emu
    engine --> exec
    engine --> ws
    gateway --> lm
    gateway -. "optional" .-> cloud
    exec --> agent
    agent --> tc
    agent --> run

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
```

## 2. Package layering

Arrows point from a package to what it may import; nothing imports `ui` or `cli`, and the engine never touches Streamlit (invariant 8). Enforced by `tests/unit/test_layering.py` once #65 lands. Delivered: bottom layers in Phase 0, `nodes`, `engine`, `ui` in Phase 1.

```mermaid
flowchart TB
    cli["cli (__main__)"]:::done
    ui["ui (Streamlit only)"]:::planned
    engine["engine (LangGraph only)"]:::planned
    nodes["nodes"]:::planned
    prompting["prompting"]:::planned
    verification["verification"]:::done
    workspace["workspace"]:::planned
    toolchains["toolchains"]:::done
    llm["llm (SDKs only here)"]:::planned
    knowledge["knowledge / memory / policy"]:::planned
    contracts["contracts"]:::done
    executors["executors"]:::done
    persistence["persistence"]:::done
    training["training"]:::done
    domain["domain (Pydantic, stdlib only)"]:::done

    cli --> engine
    engine --> nodes
    nodes --> prompting
    nodes --> verification
    nodes --> workspace
    nodes --> llm
    prompting --> knowledge
    prompting --> contracts
    verification --> toolchains
    verification --> contracts
    toolchains --> executors
    workspace --> contracts
    ui --> persistence
    engine --> persistence
    llm --> domain
    knowledge --> domain
    contracts --> domain
    executors --> domain
    persistence --> domain
    training --> domain
    toolchains --> domain

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
```

`ui` and `engine` never import each other. The edges shown are the main ones; the full table is in architecture §3.

## 3. Run lifecycle: create and edit

The outer run graph is fixed code. Green rectangles are human gates (G0-G5); each gate is a LangGraph `interrupt()` in a node that makes no LLM call. Create mode is delivered in Phase 1; edit mode for external projects in Phase 3 (barthelona-created workspaces can be edited from Phase 1).

```mermaid
flowchart TB
    req(["User request (RU / UK / EN)"])
    req --> intake["intake<br/>normalize to English goal"]
    intake --> g0{{"G0 Clarify<br/>only if ambiguous"}}
    g0 --> backlog["refine_backlog"]
    backlog --> tests["test_author<br/>acceptance tests"]
    tests --> vspec["validate_spec"]
    vspec --> g1{{"G1 Spec and tests"}}
    g1 --> arch["architect<br/>contracts.yaml"]
    arch --> vcon["validate_contracts"]
    vcon --> hgen["header_gen<br/>gen/: inc, stubs, harness, Makefile"]
    hgen --> skel["skeleton_build<br/>all-stub project passes V0-V2"]
    skel --> g2{{"G2 Contracts"}}
    g2 --> sprints["SPRINT LOOP (diagram 4)"]
    sprints --> fin["final_integration<br/>real modules only, full ladder"]
    fin --> g4{{"G4 Final: merge, export, discard"}}
    g4 --> done(["finalize<br/>branch bart/run_id, tag inc-NN"])

    edit(["Edit mode: folder or git URL"]) --> imp["import + detect_target"]
    imp --> base["baseline_build<br/>fix_build story if red"]
    base --> rmap["repo_map<br/>regex extractors + PageRank"]
    rmap --> rec["recover_contracts<br/>nm + Capstone, marked inferred"]
    rec --> char["characterize<br/>freeze current behaviour as tests"]
    char --> cspec["change_spec"]
    cspec --> g1e{{"G1"}}
    g1e --> delta{"contract delta?"}
    delta -- "yes" --> g2e{{"G2"}}
    delta -- "no" --> sprints
    g2e --> sprints
    sprints -. "stuck task, cloud consent, budget" .-> g5{{"G5 Consent and help"}}

    classDef gate fill:#c8e6c9,stroke:#2e7d32,color:#000
    class g0,g1,g2,g4,g1e,g2e,g5 gate
```

## 4. Meta-agentic sprint loop

The AI proposes, deterministic code decides: the planner emits a request, `compose` builds the graph, rules T1-T10 validate it, and an invalid graph falls back to the policy's default template after two repairs. The run is never blocked. L0 (rule-based) is the Phase 1a default and always the fallback; L1 arrives in Phase 1b as an opt-in flag, L2 in Phase 2.

```mermaid
flowchart TB
    backlog[("Backlog and contracts")] --> plan["sprint_planner<br/>(L1: LLM chooses template, insertions,<br/>knobs, per-loop budgets)"]
    plan -. "L0: rule planner, story kind picks template" .-> compose
    plan --> compose["compose (deterministic)<br/>template + insertions + policy rules<br/>+ project overlay, clamped to caps"]
    compose --> valid{"validate_topology<br/>rules T1-T10"}
    valid -- "errors, at most 2 repairs" --> plan
    valid -- "exhausted: default template,<br/>event validation_exhausted" --> persist
    valid -- "ok" --> persist["persist_topology<br/>sprints/NN/topology.json + spec_hash"]
    persist --> comp["compile_sprint (pure function)"]
    comp --> layers["run_sprint<br/>Send fan-out per task layer<br/>one task pipeline per task (diagram 5)"]
    layers --> standup["standup (deterministic)"]
    standup -- "continue" --> layers
    standup -- "escalate" --> layers
    standup -- "re-plan, bounded by max_replans" --> plan
    standup -- "descope: item back to backlog" --> backlog
    standup -- "layers done" --> integ["integration + verify_dod<br/>commit_increment, tag inc-NN"]
    integ --> g3{{"G3 Sprint review<br/>auto when green with autopilot"}}
    g3 --> retro["retro<br/>metrics, lessons, overlay changes"]
    retro -- "overlay: knobs within policy ranges,<br/>logged and revertible" --> compose
    retro -- "policy patch proposals" --> lab[("Policy Lab queue, Phase 5")]
    retro --> more{"backlog empty or<br/>sprint cap?"}
    more -- "no" --> plan
    more -- "yes" --> out(["exit to final_integration"])

    classDef gate fill:#c8e6c9,stroke:#2e7d32,color:#000
    class g3 gate
```

## 5. Task pipeline and escalation ladder

Inside one task: generate, apply, gate, climb the ladder, fix. Every loop declares bounds (iterations, time, tokens, money) and every exit has a `StopReason` (invariant 6). Code travels in FILE / SEARCH-REPLACE / SYMBOL envelopes, never JSON. Delivered in Phase 1; `candidates` (E2) in Phase 2.

```mermaid
flowchart TB
    start(["task + write scope"]) --> ctx["context assembler<br/>token-budgeted: contract, stubs,<br/>facts, rule card, repo map"]
    ctx --> gen["coder<br/>(LLM, envelope output)"]
    gen --> parse{"envelope parses?"}
    parse -- "no, up to 2 repairs" --> gen
    parse -- "yes" --> apply["apply atomically"]
    apply --> tamper{"tamper gate T<br/>(+ minimality M in edit mode)"}
    tamper -- "reject" --> reject(["attempt rejected,<br/>protected files untouched"])
    tamper -- "pass" --> ladder["verification ladder (diagram 6)"]
    ladder --> ok{"required levels green?"}
    ok -- "yes" --> commit(["commit per green task<br/>symbols frozen as tested"])
    ok -- "no" --> sig{"stall? same error_sig twice<br/>or repeated patch hash"}
    sig -- "no" --> fix["fixer<br/>E0: first error plus or minus 5 lines"]
    fix --> apply
    sig -- "yes or fix budget spent" --> esc{"next escalation step"}
    esc --> e1["E1: add facts, lessons,<br/>filtered docs, callee code"]
    e1 --> gen
    esc --> e2["E2: candidates<br/>2-3 variants ranked by the oracle"]
    e2 --> apply
    esc --> e3["E3: cloud chain<br/>only if cloud_allowed"]
    e3 --> gen
    esc --> e4{{"E4 / G5: human<br/>hint, contract_change, descope, abort"}}

    classDef gate fill:#c8e6c9,stroke:#2e7d32,color:#000
    class e4 gate
```

## 6. Verification ladder and gates

Cheapest check first; oracles decide, models only propose (invariant 1). Each level is a registered `LevelCheck` per target family (D-046); a failed level makes later ones `skipped`. MVP Definition of Done is V0-V2 plus V5/V6, labelled ABI-unverified until V3/V4 and the mutation corpus exist (Phase 2). Today V0-V2 exist; V5/V6 need the `bart-run` executor (#47).

```mermaid
flowchart LR
    apply(["after apply"]) --> t["T tamper gate<br/>hashes of tests, contracts.yaml,<br/>Makefile, gen/ regenerated"]:::planned
    t --> v0["V0 syntax only<br/>nasm / as"]:::done
    v0 --> v1["V1 assemble +<br/>nm vs registry"]:::done
    v1 --> v2["V2 link:<br/>unresolved, PIE, entry"]:::done
    v2 --> v3["V3 static ABI lint<br/>Capstone CFG"]:::planned
    v3 --> v4["V4 Unicorn tests +<br/>dynamic ABI checks"]:::planned
    v4 --> v5["V5 C-harness tests<br/>in bart-run"]:::wip
    v5 --> v6["V6 whole-program golden I/O<br/>in bart-run"]:::wip
    v6 --> dod{"Definition of Done<br/>for story kind"}:::planned
    v5 -. "AVX code routed here" .-> v4
    fail(["any failure"]) -.-> v7["V7 gdb / qemu trace<br/>context for the fixer"]:::planned
    v6 -. "opt-in, later" .-> v8["V8 real Windows<br/>Windows Sandbox"]:::planned
    t -. "edit mode" .-> m["M minimality gate<br/>diff only in declared symbol spans"]:::planned
    mut[("ABI mutation corpus<br/>100% bad detected, 0 false positives")]:::planned -. "gates trust in V3 / V4" .-> v3

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
```

## 7. Execution, sandbox and crash consistency

Top: how a command reaches a container and what the sandbox forbids (D-043, §13.4). Bottom: the write order in every side-effecting node, which makes a crash at any point replay safely (D-044). Executors are delivered in Phase 0, the images with the Phase 0 `bart-tc` / `bart-run` work, the crash spike in Phase 1.

```mermaid
flowchart LR
    node["Node needs a tool run"]:::planned --> sess["Executor Session (async)<br/>request ids, own work dir"]:::done
    sess --> tr{"transport"}
    tr -- "Windows" --> wslt["WslTransport<br/>one long-lived wsl.exe pipe"]:::done
    tr -- "Linux CI" --> loct["LocalTransport"]:::done
    wslt --> ag["agent: argv lists only,<br/>allowlist, path fence, timeouts, output caps"]:::done
    loct --> ag
    ag --> tcc["bart-tc exec<br/>assemble, link<br/>--network none, read-only, non-root"]:::wip
    ag --> runc["bart-run, fresh per batch<br/>cap-drop ALL, pids 64, 256 MB,<br/>timeout -s KILL, no network"]:::wip
    never["Never: generated code on Windows,<br/>bare WSL shell, docker socket mount,<br/>secrets in containers, shell=True"]:::rule

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
    classDef rule fill:#ffcdd2,stroke:#c62828,color:#000
```

```mermaid
sequenceDiagram
    participant N as Node
    participant W as Workspace git + .barthelona
    participant S as app.sqlite
    participant C as LangGraph checkpoint
    N->>W: 1. effect (idempotent, keyed by run, task, attempt, node)
    N->>S: 2. events with dedupe_key (replay is a no-op)
    N->>C: 3. checkpoint (paths and hashes only)
    Note over N,C: crash between any two steps: the node re-runs and every step is a no-op
    Note over N,S: on resume the gateway reuses the recorded response for the same node, attempt and prompt hash
    Note over S,C: gate_requested, increment and stop events are flushed before the checkpoint
```

## 8. Model gateway and role chains

Every role has a chain per profile that ends in the local model, so a dead or broke cloud provider is an event, never a crash (invariant 11). Calls are scheduled per (endpoint, model) because a model reload costs seconds to minutes (D-047, D-039 caching). Delivered: minimal OpenAI-compatible gateway plus `FakeGateway` in Phase 0 and 1a; all providers, breakers and caps in Phase 1b; second PC and rented GPU endpoints in Phase 2 or later (#44).

```mermaid
flowchart LR
    role["Node with a role<br/>planner, coder, fixer, reviewer, ..."]:::planned --> ctxcap["context assembler<br/>cloud input cap (F-33)"]:::planned
    ctxcap --> router["role router<br/>walks the chain for the run profile"]:::planned
    router --> skip{"provider enabled,<br/>key present,<br/>circuit closed,<br/>cloud_allowed?"}:::planned
    skip -- "no: next entry,<br/>fallback reason recorded" --> router
    skip -- "yes" --> sched["scheduler<br/>semaphore per endpoint,<br/>group by model (affinity)"]:::planned
    sched --> be{"backend (official SDKs)"}:::planned
    be --> b1["OpenAIChatBackend<br/>LM Studio, Ollama, DeepSeek, Qwen"]:::wip
    be --> b2["AnthropicBackend"]:::planned
    be --> b3["OpenAIResponsesBackend"]:::planned
    be --> b4["GeminiBackend"]:::planned
    be --> b5["FakeGateway / cassette replay<br/>tests, bench"]:::planned
    b1 --> local["Local model, 127.0.0.1:1234<br/>(always last in every chain)"]:::planned
    b1 -. "later endpoints[]" .-> lan["LAN LM Studio / cloud GPU"]:::planned
    b2 --> cloudp["Cloud providers"]:::planned
    b3 --> cloudp
    b4 --> cloudp
    sched --> ledger[("cost ledger + LLMCallRecord<br/>tokens, USD, model that served, endpoint")]:::planned
    cat[("config/models.yaml<br/>providers, models, prices, chains, budgets")]:::done -. "loaded by" .-> router
    sec["Secrets from env vars only"]:::rule -.-> be

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
    classDef rule fill:#ffcdd2,stroke:#c62828,color:#000
```

## 9. Data and workspace layout

Where each kind of truth lives (D-044): git owns artifacts, `app.sqlite` owns the operator-visible record, the checkpoint owns only the control position. Delivered: `app.sqlite` in Phase 0; workspaces and `gen/` with codegen in Phase 0; the rest with their features.

```mermaid
flowchart TB
    subgraph var["var/ (gitignored)"]
        app[("app.sqlite WAL<br/>runs, commands, events, gates, llm_calls<br/>later: exec_log, lessons, overlay_changes,<br/>policy_pointer, metrics, bench_results")]:::done
        ck[("checkpoints.sqlite<br/>LangGraph")]:::planned
        runs["runs/run_id/<br/>events.jsonl, llm/seq.json,<br/>exec/seq.argv|out|err, report.md"]:::planned
        kbd[("kb/<br/>facts.sqlite, docs_fts.sqlite,<br/>emb_cache.sqlite (Phase 3)")]:::planned
        tr["training/<br/>samples.jsonl, texts/ (opt-in)"]:::done
        lock["worker.lock"]:::planned
    end

    subgraph repo["Repository (committed)"]
        cfg["config/models.yaml"]:::done
        pol["policies/vN/<br/>prompts, templates (released = immutable)"]:::planned
        asmdoc["asm_doc/ manuals (RAG source)"]:::done
        docs["docs/: architecture, ADRs, roadmap"]:::done
    end

    subgraph wsp["Workspace = its own git repo, branch bart/run_id"]
        proj["project.yaml<br/>spec, target profile, build recipe"]:::planned
        con["contracts.yaml<br/>single source of truth for interfaces"]:::planned
        src["src/*.asm | *.s<br/>LLM-written, only inside a task's write scope"]:::planned
        gen["gen/ GENERATED, hash header<br/>inc, stubs, contracts.h, harness"]:::wip
        tst["tests/ (locked, hashed)<br/>acceptance, unit, reference, characterization"]:::planned
        bart[".barthelona/<br/>backlog.yaml, sprints/NN/{plan,topology,review,retro},<br/>repomap.json, policy_overlay.yaml"]:::planned
    end

    con -- "codegen, never hand- or LLM-written" --> gen
    con -. "frozen while coding" .-> src
    tst -. "frozen while coding" .-> src
    pol -- "selected per run" --> bart
    kbd -- "retrieval" --> src

    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#000
    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
```

## 10. Phases and what each one adds

Each phase ends only when its exit criteria and the phase review (D-037) pass. Phase 1 is split into 1a (walking skeleton, L0 only) and 1b (breadth). Assembler first: other languages and WASM come after the assembler phases.

```mermaid
flowchart LR
    p0["Phase 0 (in progress)<br/>Foundations, deterministic spine<br/>executors, NASM/GAS adapters, V0-V2 done<br/>to do: images, V5/V6, codegen, tamper gate,<br/>minimal gateway, bake-off"]:::wip
    p1a["Phase 1a<br/>Walking skeleton<br/>L0 planner, one backend, G1/G2/G4,<br/>UI: New request, Approvals, Live run,<br/>crash spike"]:::planned
    p1b["Phase 1b<br/>Breadth<br/>validator T1-T10, compile, L1, re-planning,<br/>all providers, breakers, bench v1"]:::planned
    p2["Phase 2<br/>Stronger oracles, full meta-agency<br/>V3 + V4, mutation corpus, L1 default,<br/>L2 flag, retro overlay, compile_high_level"]:::planned
    p3["Phase 3<br/>Edit external projects, memory<br/>importer, repo map, inferred contracts,<br/>lessons, optional Qdrant"]:::planned
    p4["Phase 4<br/>Dialect and target breadth<br/>FASM, Win64, ELF32, MASM syntax,<br/>boot sector, then WAT (F-34)"]:::planned
    p5["Phase 5<br/>Policy Lab, research, extras<br/>A/B on holdout, gated web research,<br/>AArch64 / RISC-V, MCP server"]:::planned

    p0 --> p1a --> p1b --> p2 --> p3 --> p4 --> p5

    x0["Exit: two 3-module projects (NASM, GAS) pass verify,<br/>bake-off table, local model chosen"]:::exit
    x1["Exit: crash spike passes, hybrid beats single-prompt by +30,<br/>owner builds a 3-module NASM program via the UI"]:::exit
    x2["Exit: mutation corpus 100% detected, 0 false positives"]:::exit
    x3["Exit: zero characterization regressions on external seeds"]:::exit
    x4["Exit: each preset passes its conformance kit"]:::exit
    x5["Exit: one policy patch activated with measured gain, rollback exercised"]:::exit
    p0 -.-> x0
    p1b -.-> x1
    p2 -.-> x2
    p3 -.-> x3
    p4 -.-> x4
    p5 -.-> x5

    classDef wip fill:#ffe0b2,stroke:#ef6c00,color:#000
    classDef planned fill:#eceff1,stroke:#607d8b,color:#000
    classDef exit fill:#e3f2fd,stroke:#1565c0,color:#000
```
