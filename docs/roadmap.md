# Roadmap

Phased plan for barthelona. Each phase has a goal, deliverables and exit criteria. A phase is done only when its exit criteria are met; the benchmark decides whether optional subsystems are switched on.
Every phase's exit criteria also include the phase review (D-037): it ran, and its blocking issues are fixed.
Architecture: `docs/architecture.md`. Decisions: `docs/adr/`.

Current status (2026-10-14): **Phase 0 in progress** — repository and environment done (design, agent configuration for Claude Code and Codex, conda scripts, hash-locked dependencies, baseline tests); code skeleton started: domain models, the `var/app.sqlite` store and the `python -m barthelona` entry point exist; the toolchain probe and `verify` are next.

## Phase 0 — Foundations and the deterministic spine (about 1–2 weeks, no agent loop yet)

**Goal:** prove the toolchain, the generators and the verification oracles without any LLM, and choose the local model on measured numbers.

**Deliverables**
- Repository: `AGENTS.md` / `CLAUDE.md`, `.claude/` config and the Codex mirror ✔, `.gitattributes` ✔, `pyproject.toml` ✔, `environment.yml` ✔, hash-locked requirements ✔, `create_env` / `activate` / `lock` scripts ✔, `doctor.ps1` ✔, dependency fingerprint + baseline tests ✔.
- Code skeleton: domain models (Pydantic v2) ✔; persistence (SQLite WAL schema and migrations for `runs`, `commands`, `events`, `gates`, `llm_calls`) ✔; `python -m barthelona` CLI (entry point with `version` and `schema` ✔; `verify` and `probe` land with their deliverables).
- Training data (D-036): `TrainingSample` model, the off-by-default setting, the local dataset writer and reader with secret redaction, `python -m barthelona training status` ✔.
- Environment fixes (owner actions): `.wslconfig` memory cap; Qdrant storage moved to a named volume (see `docs/runbook.md`).
- Execution: Docker images `bart-tc` (`docker/toolchain`) and `bart-run` (`docker/runner`) with a CI smoke test (`scripts/docker-smoke.sh`) ✔ (base `ubuntu:26.04` by tag; digest pinning comes with `barthelona probe`); the WSL agent (JSON lines, staging, allowlist, path fence); `barthelona probe` writing `config/toolchains.lock.json`.
- Assemblers: NASM and GAS (Intel and AT&T) dialect adapters; ld/gcc linkers; diagnostics parsers with real captured fixtures.
- Codegen: contract registry → `.inc` files, stubs, `contracts.h`, C harness, Makefile, with golden tests.
- Verification: ladder levels V0, V1, V2, V5, V6 plus the tamper gate; first ABI mutation corpus entries; `barthelona verify`.
- Models: minimal gateway (OpenAI-compatible backend + FakeGateway); bake-off harness (10 single-prompt tasks per candidate: tok/s, JSON-schema validity, pass@1).

**Exit criteria**
- Two hand-written 3-module projects (one NASM, one GAS) pass V0–V2, V5 and V6 through `barthelona verify`.
- An all-stub skeleton generated from a sample `contracts.yaml` builds.
- Parser and codegen tests are green.
- A bake-off table exists; one main local model is chosen and loaded in LM Studio at 16K context.
- The single-prompt baseline score is recorded.
- The phase review (D-037) ran, and its blocking issues are fixed.

## Phase 1 — MVP vertical slice (about 3–4 weeks)

**Goal:** an end-to-end Meta-Agentic Scrum run from the Streamlit UI, from request to merged repo, on the linux-x64 NASM/GAS presets.

**Delivery order (architecture review, 2026-10-17, issue #69):** slice **1a, walking skeleton** first: L0 templates only, one OpenAI-compatible backend plus `FakeGateway`, envelope parser, context assembler, ladder and tamper gate, outer run graph with G1/G2/G4, worker and event log, UI pages New request, Approvals and Live run, and the crash spike on that graph. Slice **1b, breadth** follows: validator T1-T10, `compile`, L1, re-planning, the other providers, breakers and caps, the training-data hook, remaining pages. The exit criteria below apply to the end of 1b; 1a ends with one 3-module NASM program from a request and the single-prompt baseline vs. L0 recorded.

**Deliverables**
- Engine: outer run graph (create mode, and edit mode for barthelona-created workspaces); gates G0, G1, G2, G4, G5 (G3 auto when green); node registry; `compose`; validator T1–T10 with Hypothesis property tests; `compile`; topology persistence and revisions.
- Sprint composition: L0 rule planner, plus **L1 via `planner.composition_level: L1`** (experimental, D-028); multi-unit `LoopBound`s; stall detector; bounded re-planning.
- Policy v1: templates `module_create`, `symbol_patch`, `fix_build`, a minimal `contract_change`, `integration`; role prompts. The minimality gate ships here too, for barthelona-created projects (symbol spans come from `contracts.yaml`), so edit-mode pipelines satisfy T6.
- Prompting: envelope parser (FILE / SEARCH-REPLACE / SYMBOL); context assembler with token budgets.
- Model gateway: backends for LM Studio/Ollama (OpenAI-compatible), Anthropic, OpenAI, Gemini and DeepSeek; `config/models.yaml` catalog; per-call ledger; optional caps; error taxonomy, retries, circuit breakers and fallback chains ending in the local model (D-029, D-030).
- Training data (D-036): the engine records each code-producing attempt after the ladder when `Run.collect_training_data` is set, passing the gateway's key values to the redactor and refusing runs on `bench/tasks/holdout` tasks (unit test); the New request checkbox; `barthelona training export` (supervised pairs from accepted attempts, preference pairs from `improves_on_seq`; local-model samples only unless the owner opts in per provider).
- Run control: budgets, `StopReason`, escalation E0, E1, E3, E4; branch per run, commit per green task, tag per increment.
- Knowledge: `facts.sqlite` (NASM App. F, directive indexes, `syscall_64.tbl`, SysV ABI row); FTS5 docs; rule cards for nasm / gas-intel / gas-att on linux-x64.
- Process: `scripts/run.ps1` (worker + Streamlit); worker with event log + JSONL mirror; Streamlit pages New request, Approvals, Sprint board (topology DOT), Live run, Review, Toolchains & models (with provider health), Runs.
- Benchmark v1: 12 create + 8 edit tasks (dev + holdout); cassette replay.
- Crash/resume spike, with crash points after the effect, after the event, mid-batch and during a gate (D-044).

**Exit criteria**
- Crash/resume spike passes (kill mid-task and during a gate; no finished node re-runs), or the interpreter fallback is adopted and passes the same test.
- Graph tests green with FakeGateway: happy path, fix loop, stall, re-plan, escalation, refusal, provider failover, budget stop, tamper rejection.
- Dev-split bench: the hybrid profile beats the single-prompt baseline by the margin set in Phase 0 (initial target +30 points); local-only recorded; zero tamper escapes; L0 vs L1 recorded.
- The owner creates a 3-module NASM program from a Russian-language request through the UI and approves it at the gates.
- Stance until Phase 2: increments are accepted on the MVP DoD (V0–V2 + V5/V6) and labelled **ABI-unverified** in the UI and the increment record, until the V3/V4 oracles and the mutation corpus are in place.
- The phase review (D-037) ran, and its blocking issues are fixed.

## Phase 2 — Stronger oracles and full meta-agency

**Goal:** stronger verification, plus the complete Meta-Agentic layer.

**Deliverables**
- V3 Capstone static ABI lint; V4 Unicorn ABI checker (canaries, alignment, red zone, DF, syscall allow-list, registry mocks, DWARF mapping; AVX routed to V5); full ABI mutation corpus.
- Policy v2: templates `candidates` (E2) and the `trace_capture` slot (V7).
- **L1 on by default** if the bench shows no regression; **L2** (AI composes whole pipelines from node types) behind a flag for strong tiers.
- Retrospective report and overlay changes with revert in the UI; lesson candidates stored, not yet injected.
- _(experimental, gated by bench)_ `compile_high_level` node type: LLM generates C,
  `gcc -O2 -S` inside `bart-tc` produces the `.s` patch; GAS presets first; enabled only
  if bench ≥ direct-codegen + 5 pts on Phase 2 holdout split (D-040, #follow-up).

**Exit criteria**
- Mutation corpus: 100% of bad cases detected, 0 false positives.
- Every AI-composed topology either validates or falls back to L0; no run is blocked.
- Bench: Phase 2 ≥ Phase 1 on dev and holdout; L2 enabled for a profile only if it beats L1 there. Results recorded in an ADR.
- The phase review (D-037) ran, and its blocking issues are fixed.

## Phase 3 — Edit mode for external projects, memory, optional vector search

**Deliverables:** importer and target detection; baseline build with `fix_build`; repo map (regex extractors + PageRank); inferred contracts (nm + Capstone); characterization tests; localizer; minimality gate extended to external projects (symbol spans from the repo map); full `contract_change` flow; lessons lifecycle with regression checks and an inbox; retrieval eval (≥60 queries); Qdrant hybrid backend behind the Retriever interface; MASM docs from cpp-docs.

**Exit criteria:** external seed repos edited with zero characterization regressions; Qdrant on by default only if recall@5 beats FTS5 by the agreed margin; lesson injection on only if the bench improves; the phase review (D-037) ran, and its blocking issues are fixed.

## Phase 4 — Dialect and target breadth

**Deliverables:** FASM 1 (ELF64, PE64; frame-based diagnostics; `-s` line mapping; `public`/`extrn` headers); optional fasmg/fasm2; Win64 targets (NASM/GAS + mingw, wine runner, shadow-space and `.pdata` checks); ELF32 cdecl; asmc/UASM for MASM syntax; ml64 opt-in on Windows (VS Build Tools, admin); boot-sector preset with qemu-system. Each preset ships a rule card, a conformance kit and bench tasks.

**Exit criteria:** each preset passes its conformance kit and solves at least 5 bench tasks within budget; the phase review (D-037) ran, and its blocking issues are fixed.

## Phase 5 — Policy Lab, gated research, extras

**Deliverables:** Policy Lab (PolicyPatch → candidate version → A/B on holdout, ≥3 repeats, batch APIs → G6 activation/rollback); gated web research (approval, domain allowlist, low-trust candidates promoted only after a fix passes); optional advisory critic on a different model; OpenTelemetry → Phoenix; OpenVINO Model Server trial; AArch64/RISC-V via qemu-user; a local MCP server exposing barthelona's toolchain and verification tools (usable by Claude Code during development); KolibriOS if chosen.

**Exit criteria:** at least one policy patch activated with a measured holdout gain; a rollback exercised; web-sourced knowledge never reaches prompts without the evidence step; the phase review (D-037) ran, and its blocking issues are fixed.

## Open decisions (owner)

Each has a recommended default that the docs already assume. Change any of them and the affected ADR is updated.

| # | Question | Recommended default | Why it matters |
| --- | --- | --- | --- |
| 1 | Which cloud providers are enabled by default, and for which roles? | All four configured; per-run consent; roles follow `config/models.yaml` (planner and escalation: flagship-first, Opus 5.5 → GPT-6.1 Sol → Gemini 3.1 Pro → DeepSeek V4 Pro; cloud worker: mid tier; cheap tier reserved); no dollar cap unless set | Quality, speed, cost, and whether code leaves the machine |
| 2 | Which local models to use for the Phase 0 bake-off? | First the installed ones in `C:\models` (all fit in 32 GB RAM): LFM2-24B-A2B and LFM2.5-8B-A1B (MoE, fast), Qwen2.5-Coder-7B (worker), DeepSeek-R1-Distill-Qwen-14B and Ministral-3-14B-Reasoning (planner, slow), granite-4.1-8b; skip Codestral-22B Q2_K and Bonsai-27B Q1_0 (too heavily quantized); verify the provenance of the DeepSeek-V4-Flash GGUF before loading it. Then download Qwen3-Coder-30B-A3B and gpt-oss-20b. Stronger models run on the second PC (`lan_lmstudio`) or a rented GPU (`cloud_gpu`) | The local model dominates quality and latency; only one large model fits in RAM; dense 14B models decode at only a few tok/s on this CPU/iGPU |
| 3 | Configure `%UserProfile%\.wslconfig` (no file exists yet)? | `[general] instanceIdleTimeout=-1` (WSL stays up, so both Qdrants and the Qdrant MCP stay reachable) plus `[wsl2] memory=8GB`, `processors=8`, then `wsl --shutdown` (runbook section 3) | WSL otherwise stops ~15 s after the last WSL process exits; a ~20 GB local model + Windows + WSL at its default size oversubscribes 32 GB |
| 4 | Which dialect comes after NASM/GAS? | FASM 1 → Win64 (mingw + wine) → asmc/UASM → ml64 last (opt-in, admin) | Sets Phase 4 order, images, rule cards and bench tasks |
| 5 | KolibriOS as a target? | Optional, Phase 5+ | Weak oracles and high setup cost; would distort the MVP |
| 6 | How to install toolchains? | Pinned Docker images for the product; optional `apt-get install nasm yasm fasm gdb` in WSL for manual debugging | Reproducibility and isolation vs convenience |
| 7 | `asm_doc/` and the Gemini draft in git? | Owner committed `asm_doc/` (2026-10-13, not pushed). Before the first push, decide whether to keep it (licenses: GFDL binutils, Microsoft CC-BY-4.0 MASM, unclear fasm terms) or untrack it (`git rm -r --cached asm_doc` + `.gitignore`). Draft kept in `docs/archive/` as non-authoritative | License hygiene for a BSD-2 public repo; repository size (~19 MB) |
| 8 | Qdrant storage and usage? | Move storage from the `/mnt/c` bind mount to a named Docker volume now; product uses FTS5 until the Phase 3 eval | Qdrant documents data loss on Windows/WSL shared mounts |
| 9 | Which human gates are manual by default? | G1, G2, G4 manual; G3 auto when green (autopilot checkbox); G5 always manual | Control vs throughput for long local runs |
| 10 | Where do workspaces live? | `<repo>/workspaces/` (gitignored), overridable by `BARTHELONA_WORKSPACES` and per project in the UI | Each workspace is its own git repo |
| 11 | Maximum composition level per profile? | Phase 1: L0 by default, L1 opt-in per run; from Phase 2: L1 by default if the bench agrees; L2 only for hybrid/cloud after the Phase 2 bench | How much graph design is delegated to which model |
| 12 | Dialect strategy for `compile_high_level` node on NASM presets? | (a) treat gcc -S output as a GAS module in the same project (mixed dialect, simplest), or (b) use `objdump -M intel` + a converter to produce NASM-compatible syntax (complex), or (c) restrict this node to GAS presets only for v1 | Compiler output is GAS syntax; NASM projects cannot assemble it directly (D-040) |

## Follow-ups (deferred items)

Items deferred while working, by an agent, the owner or a reviewer. Check this table before picking the next deliverable. A row leaves only when it is fixed (cite the commit) or the owner drops it (date). Bugs in code being changed are fixed in the same change, not parked here.

| # | Item | Found while | Why deferred | Suggested fix | Status |
| --- | --- | --- | --- | --- | --- |
| F-1 | `.claude/rules/python.md` says "an import-linter test will enforce" the layering, but `import-linter` is not a dependency | conduit config review, 2026-10-13 | No packages exist yet | Stdlib test `tests/unit/test_import_isolation.py`: import each entry point in a fresh interpreter and assert `langgraph`/engine modules never load under `ui` and `streamlit` never loads under the engine. Or add import-linter via `update-deps` and an ADR. Then fix the rule sentence. | superseded by D-045 / #65 (partial 2026-10-13: `test_domain_imports_no_io_or_framework_modules` covers `domain`) |
| F-2 | Path guards matched paths relative to the repo root, so writes under `.claude/worktrees/<x>/` bypassed the protected-path patterns | conduit config review, 2026-10-13 | — | `guard-paths.ps1` and `post-edit.ps1` strip the worktree prefix; `test-hooks.ps1` covers it | fixed (2026-10-13, setup commits) |
| F-3 | The editable install fetches its build backend (hatchling) from PyPI without a hash lock | second review, 2026-10-13 | Small risk; documented in the runbook and D-031 | Lock hatchling in a build lock and install with `--no-build-isolation` | open |
| F-4 | `scripts/create_env.sh` has no executable bit in git (Windows checkout) | second review, 2026-10-13 | Only matters on a Linux clone | `git update-index --chmod=+x scripts/create_env.sh scripts/dev.sh` | fixed (2026-10-13, setup commits) |
| F-5 | The `kb`, `obs` and `ingest-pdf` extras are declared but not locked; installing them today would be ad hoc | review gate, 2026-10-13 | Not needed before Phase 3/5 | Before an extra is first used, add its lock profile to `lock.ps1` and `create_env` (or drop the extra until its phase) | open |
| F-6 | `unicorn` (runtime dependency for the V4 emulator) is GPL-2.0 per upstream, while barthelona is BSD-2-Clause | review gate, 2026-10-13 | No distribution planned yet | `docs-researcher` confirms the license and the implications of importing it; record the decision (keep in the separate emulator process, relicense, or replace) in an ADR before distributing | resolved 2026-10-13 by owner decision: installed `unicorn` 2.1.4 metadata says BSD License (capstone BSD, lief Apache-2.0, pyelftools public domain). Re-check the bundled native core's license before distributing binaries |
| F-7 | Local endpoint overrides (`LMSTUDIO_BASE_URL`, `OLLAMA_BASE_URL`) could use `localhost` or a non-loopback host | review gate, 2026-10-13 | No catalog loader yet | The Phase 1 catalog loader rejects `localhost` and, for `local: true` providers, non-loopback hosts; non-loopback hosts are allowed only for `local: false` providers (`lan_lmstudio`, `cloud_gpu`), and `cloud_gpu` must be https; unit test | open |
| F-8 | `guard-shell.ps1` checks `..` before stripping `./`, so `rm -rf ./..`, `rm -rf docs/../..` and `rm -rf <repo>/..` are not blocked | delta review gate, 2026-10-13 | Guard changes need the owner's approval | Block any recursive-delete operand with a `..` segment after normalization; add harness cases | done 2026-10-13 (owner approved; hook cases added) |
| F-9 | The `--output` block covers `git diff/log/show/format-patch` but not `git diff-tree/-index/-files` (auto-allowed by `Bash(git diff*)`); case-insensitive `-o` also blocks `git diff -O <orderfile>` | delta review gate, 2026-10-13 | Guard change | Match `^(diff(-tree\|-index\|-files)?\|log\|show\|whatchanged\|range-diff\|format-patch)$` with case-sensitive `-o`; add cases | done 2026-10-13 (owner approved; hook cases added) |
| F-10 | `.env` operands are only checked for reader/grep/source commands; e.g. `git diff --no-index /dev/null .env` prints the file and is auto-allowed | delta review gate, 2026-10-13 | Guard change | Block any unquoted `.env*` operand (except `.env.example`) for every command, allowing `ls`, `test`, `git check-ignore` | done 2026-10-13 (owner approved; hook cases added) |
| F-11 | The allow rule for `deps_fingerprint.py*` also pre-approves `--write` (re-stamping locks without a prompt) | delta review gate, 2026-10-13 | Permission change | Narrow to `deps_fingerprint.py --check*`; `lock.ps1` runs `--write` itself | done 2026-10-13 (owner approved; hook cases added) |
| F-12 | Small cleanups: models.yaml 127.0.0.1 comment placement and indent; `dev.sh` `conda env list` under `pipefail` and prefixes with spaces; a shared `is_read_only()` for the sync and its test; runbook wording for the stamp (now covers locks); `lock.ps1` fingerprint python should reuse `$EnvPython` | delta review gate, 2026-10-13 | Cosmetic / robustness | Fix in the next change that touches these files (gated paths: run the review gate) | open |
| F-13 | `config/models.yaml` gained the `network:` key (`lan`, `internet`) and an hourly-billed provider (`cloud_gpu`), neither described in architecture §16.2 or D-030 | review gate, 2026-10-13 | Both providers are disabled; no loader yet | With the Phase 1 catalog loader: document `network:` and hourly billing in §16.2 (amend D-030), validate the key, test it | open |
| F-14 | Guard leftovers: `declare -x NAME=1` / `typeset -x` (sets, not prints) is blocked as an env dump; quote splitting (`cat .en'v'`) still bypasses the `.env` operand check | delta review gate, 2026-10-13 | Low impact; guard change needs owner approval | Block `-x` only without a NAME operand; compare tokens after joining adjacent quoted parts; add harness cases | open (owner approval) |
| F-15 | `AGENTS.md` Environment still says Qdrant (:6333) is unreachable while WSL is stopped; the product's Qdrant is now `barthelona-qdrant` on :6343 (D-034) | 2026-10-13 | Gated file; out of the reviewed diff | Mention both ports in the next AGENTS.md change (review gate) | fixed in 16a6ecf (PR #4) |
| F-16 | No CI workflow: agents' self-merge (D-035) rests on review/scan apps and a local `verify`, none of which builds or runs tests on GitHub | review gate on D-035, 2026-10-13 | Out of scope for the approval change | Add a GitHub Actions workflow running ruff, mypy, pytest and the mirror/lock checks; make it required | fixed 2026-10-14 (`.github/workflows/ci.yml`, issue #15); making the checks required in branch protection is an owner action |
| F-25 | No Markdown linter (80 `.md` files) and no `pre-commit` hooks; CI and the local `verify` are the only gates | Sonar and tooling review, 2026-10-14 (issue #15) | A first markdownlint pass over `docs/` would be a large, separate diff | Add `markdownlint-cli2` in CI with a config matching the docs style, fix its findings in one docs commit; then decide on `pre-commit` (needs `update-deps`) | open |
| F-26 | SonarCloud runs automatic analysis, so it gets no test coverage and does not gate PRs on our own config | Sonar and tooling review, 2026-10-14 | Needs a `SONAR_TOKEN` secret (owner action) | Switch to CI-based analysis: `pytest --cov` + the SonarQube scan action in `ci.yml`, move `.sonarcloud.properties` into `sonar-project.properties` | open (owner) |
| F-28 | Guard hooks have empty `catch { }` blocks; in `guard-paths.ps1:65` an unreadable `MANIFEST.json` lets an edit to a released policy through (fail-open on invariant 7). CI skips `PSAvoidUsingEmptyCatchBlock` and `PSUseSingularNouns` for `.claude/hooks/` until this is fixed | Sonar and tooling review, 2026-10-14 (issue #22) | Guard hooks change only on the owner's decision | Block on a manifest parse error, comment the `GetFullPath` fallback, add harness cases; then drop the CI exclusion | open (owner) |
| F-27 | Fuzzing beyond the domain validators: the envelope parser, topology validator T1-T10, diagnostic parsers and generated assembly through the oracles are not fuzzed | Sonar and tooling review, 2026-10-14 (issue #20) | That code does not exist yet | Hypothesis property tests land with each parser/validator; for assembly, mutate generated sources (mutation corpus, §13) and require the oracles to reject every broken variant | open |
| F-17 | `docs/roadmap.md` open decision 7 and D-027 say `asm_doc/` is not pushed, but origin/main has it since 3bef7db | review gate on D-035, 2026-10-13 | Owner decision on publishing third-party docs | Owner decides: keep (fix both texts and check licenses) or remove from history | open (owner) |
| F-18 | Guard gaps after D-035: a bare `git push` while on `main`, and `git checkout HEAD -- <dir>` (discards a directory), are not blocked; nor are abbreviated long options (`--amen`, `--forc`, `--discard`) or `git stash -q drop` | review gate on D-035, 2026-10-13 | Needs the current branch / pathspec analysis in the hook | Resolve the current branch and its upstream for refspec-less pushes; block `checkout <tree> -- <dir>` for directories; match option prefixes of 3+ chars; find the stash subcommand after options; add harness cases | open |
| F-19 | `Lesson.regression_check.asm` puts assembly inside the Lesson JSON document, which `retro` (an LLM node) proposes; this conflicts with invariant 5 / D-011 if filled through a JSON schema | review gate, domain models, 2026-10-13 | Needs an owner decision; no retro node yet | Fill `asm` deterministically from the evidence diff, or carry it in a FILE envelope referenced by path; record in §15.2 and D-017 | open (owner) |
| F-20 | `RunEvent.payload`, `GateRequest.payload` and `GateDecision.edits` are free-form dicts; code or secrets could end up in event JSON | review gate, domain models, 2026-10-13 | The model layer cannot enforce it | With persistence: cap the payload size and route code and bulky data to `payload_ref`; unit test | open (partial 2026-10-14: the store refuses event payloads, gate payloads and gate-decision `edits` over 16 KiB with a pointer to `payload_ref`; routing code to `payload_ref` lands with the nodes that emit it) |
| F-21 | `SprintTopology` compares a `pipelines` key with `pipeline.hash` only when the hash is set; a pipeline with `hash=None` can sit under any key | delta review gate, domain models, 2026-10-13 | Belongs with rule T2 | The T2 validator checks `key == spec_hash(pipeline)` for every pipeline; unit test | open |
| F-22 | `Store.set_run_status` accepts any status after any other (for example `stopped` back to `running`); the architecture defines no run-status transitions | review gate, persistence, 2026-10-14 | The engine run graph does not exist yet | With the outer run graph: write the allowed transitions in architecture §17, enforce them in `set_run_status`, unit test | open (#10) |
| F-23 | The UI shares one read-only SQLite handle across Streamlit threads (§17), which is safe only on a serialized SQLite build (`sqlite3.threadsafety == 3`) | review gate, persistence, 2026-10-14 | No UI yet | Check `sqlite3.threadsafety` in `env-doctor` and where the UI opens its handle; fail with a clear message. The UI also handles `connect_readonly`'s `RuntimeError` when the worker has not migrated yet ("worker not started") | open (#11) |
| F-24 | The training dataset has no size limit or retention; it grows with every collecting run | D-036, 2026-10-14 | Nothing writes samples before the Phase 1 engine hook | With the engine hook: show the dataset size in `training status` and on the Toolchains & models page; add `training prune --before <date>` if the size becomes a problem | open |
| F-37 | Two resume commands for one open gate can both be queued; the second fails at the worker with `ConflictError` from `resolve_gate` | review gate, PR #8, 2026-10-14 | The worker command loop does not exist yet | In the command loop, turn that `ConflictError` into a `RunEvent` (no silent fallbacks, `.claude/rules/python.md`) and test it, or refuse a second unclaimed resume per `gate_id` at enqueue | open (#12) |
| F-38 | WSL agent allow-list permits `sha256sum <path>` without fencing the path to `~/.cache/barthelona/` (R-1b) | architecture-guardian review, PR #38, 2026-10-16 | Low risk in Phase 0 (only internal code reaches the agent); grows in later phases | Add `_validate_sha256sum_paths` check analogous to `_validate_tar_paths` in `_handle()` | open (#39) |
| F-39 | `docker inspect` is not in the WSL agent allow-list; `probe_image_digest()` always returns `""` in production (N-1) | architecture-guardian review, PR #38, 2026-10-16 | Functional gap only; no security regression | Add `("docker", "inspect")` to `_ALLOWED_PREFIXES` with a guard that `argv[2]` is not a filesystem path | open (#40) |
| F-40 | `FakeExecutor.run()` does not honour `ExecLimits.max_stdout_bytes` / `max_stderr_bytes`; callers relying on the Protocol contract see uncapped output in tests (N-2) | architecture-guardian review, PR #38, 2026-10-16 | Test-only gap | Either truncate in `FakeExecutor.run()` or add a note to `Executor` Protocol docstring that truncation is best-effort | open (#41) |
| F-29 | V1 only assembles; the `nm`/registry symbol check (exports exact, undefined ⊆ imports ∪ allow-list, §13.1) is deferred until `contracts.yaml` is populated | PR #43, 2026-10-16 | `contracts.yaml` does not exist yet | Implement `run_v1` nm gate once `contracts.yaml` schema and population land; good/bad mutation corpus entries required | open (#45) |
| F-30 | NASM and GAS `parse_diagnostics` parse captured tool output (`toolchains/_diagnostics.py`, fixtures under `tests/fixtures/diagnostics/`) | PR #43 | — | — | fixed 2026-10-17 (#46); fixtures captured with nasm 2.16.01 and as 2.42 from the cloud host, re-capture in `bart-tc` and Hypothesis tests tracked in #74 |
| F-31 | V5 (C-harness tests) and V6 (golden I/O) are Phase 0 deliverables that require the `bart-run` sandbox image, which does not yet exist | PR #43, 2026-10-16 | `bart-run` image not built | Implement `run_v5` and `run_v6` once `bart-run` ships; extend `_LEVEL_ORDER`; test with `FakeExecutor` | open (#47) |
| F-32 | D-042b/c/d: provider host allow-list in the catalog loader, benchmark-gated adequacy check (Jev candidate), and the matching architecture.md §5/§13 updates | D-042 (issue #29), 2026-10-17 | Needs the Phase 1 catalog loader and the bench | Implement per D-042; update `docs/architecture.md` §5.3, §13 and §16 in the same change; keep issue #29 as the tracker | open |
| F-33 | The cloud input cap (§16.4) is a rule only: no assembler exists to enforce it, and cloud profiles have no per-role token budgets yet | token-saving research, 2026-10-17 | No context assembler or gateway code yet | With the context assembler: read `long_context.above_input_tokens` from the catalog, cap cloud input there unless the chain entry opts in (define the opt-in key in the catalog schema), define cloud per-role budgets; unit test with `FakeGateway` | open |
| F-34 | WebAssembly (WAT/wasm) as a dialect + target: `wasm-tools` or WABT as the oracle, Binaryen `wasm-opt`, wasmtime inside `bart-run` with fuel limits (Node as an optional second host); V3 ABI lint replaced by an import/export signature check | owner request, 2026-10-17 (issue #58) | Phase 4 (dialect and target breadth); low priority, assembler dialects come first (owner, 2026-10-17); not before the Phase 0 exit | Owner chose WAT only, wasmtime inside `bart-run`, pure compute first, Node opt-in later (2026-10-17, #58); at build time: `new-adr` (enum values, ABI model, execution inside `bart-run`) and `add-dialect` | open (#58) |
| F-35 | Scope question: HTML/JavaScript/CSS (and Node) as non-assembler targets; options A (wasm host glue only), B (web as a separate project type), C (out of scope) | owner request, 2026-10-17 (issue #60) | Low priority, behind the assembler phases (owner, 2026-10-17); revisit B only after the Phase 4 exit | Owner chose A (2026-10-17, #60); A rides on #58; B (web as its own project type) needs `new-adr` | open (#60) |
| F-36 | Scope boundary for other languages: C/Rust only as compile inputs (D-040, Phase 2, bench-gated); assembly dialects plus WAT as the only targets | owner question, 2026-10-17 (issue #61) | Not a priority, assembler first (owner, 2026-10-17); revisit after the Phase 4 exit | Confirm in #61; any new language target needs `new-adr` with its own oracles | open (#61) |
| F-41 | Executor contract is synchronous, shares one mutable work directory and one unmultiplexed pipe, and exists only on Windows | architecture review, 2026-10-17 (D-043) | Phase 0 code predates the engine | Async `Session` API, request ids in the agent, `AgentExecutor(transport)` with `WslTransport` and `LocalTransport`, `docker` pytest marker; before the `bart-run` executor and V5/V6 | open (#63) |
| F-42 | No rule for which store wins after a crash; events are not idempotent; no run compatibility version | architecture review, 2026-10-17 (D-044) | Needs the engine | `RunEvent.dedupe_key`, response reuse on resume, `Run.engine_state_version`, crash spike at each seam | open (#64) |
| F-43 | Layering test and SDK containment (replaces F-1) | architecture review, 2026-10-17 (D-045) | Nothing enforces the matrix yet | `tests/unit/test_layering.py` with the table as data | open (#65) |
| F-44 | Ladder is a hard-coded V0-V2 list | architecture review, 2026-10-17 (D-046) | V5/V6 (#47) are next | `LevelCheck` registry, `run_ladder`, unsupported vs skipped semantics | open (#66) |
| F-45 | Windows path traps are not covered by the path fence (reserved names, trailing dots, ADS, case collisions) | architecture review, 2026-10-17 | The envelope parser does not exist yet | One `safe_relative_path()` with tests and fuzzing | open (#67) |
| F-46 | No retention for `var/runs`, LLM call files, exec logs, events | architecture review, 2026-10-17 | Nothing writes them yet | Policy in §18, `runs prune`, size in doctor and the UI | open (#68) |
| F-47 | Phase 1 is one large slice resting on an unmeasured local-model assumption | architecture review, 2026-10-17 | Owner's roadmap | Split into 1a walking skeleton (L0 only) and 1b breadth | open (#69) |
| F-48 | `unicorn`: upstream `COPYING` and README say GPLv2, PyPI/pyproject metadata says BSD; unresolved (same as F-6) | architecture review, 2026-10-17 | V4 is Phase 2 | Confirm the wheel's bundled licence files; keep it inside the emulator child package either way | open (#70) |
| F-49 | Doc drift: duplicated price tables in §16, stale ADR ranges, F-30 cited as F-27 in `dialect.py` | architecture review, 2026-10-17 | Small | Point to `config/models.yaml`; fix the citation with Phase 0 work | open (#71) |

## Parked ideas (not scheduled)

Ideas that are not defects. At each phase start, move every row into that phase's deliverables or delete it, with a one-line reason in the devlog. At most about 25 rows; no done-archive (git keeps history). A row that would change an invariant needs `new-adr` first.

| Idea | Raised | Trigger | Why parked |
| --- | --- | --- | --- |
| Compile-down strategy (`compile_high_level` node, D-040): LLM writes C → `gcc -O2 -S` in `bart-tc` → assembly patch; bench-gated; requires owner decision on NASM dialect (open decision 12) | 2026-10-16, research thread | Phase 2 (L2 node types) | Phase 0/1 still in progress; bench gate not yet in place |
| Four HF papers (2610.17953, 2505.11480, 2603.08706, 2605.21470) on LLM+compiler topics could inform the compile-down design; network blocked in cloud container during research | 2026-10-16, research thread | Before implementing D-040 | Read from the owner's machine; Aleksandr provided the links |
| `verify-runner` agent (cheap model, read-only, no git-state changes) behind `verify` via `context: fork`, with ENV vs CODE triage for `wsl`/`llm` tests | 2026-10-13, conduit review | `pytest -m wsl` or `barthelona verify` output gets long (Phase 0) | Gate output is short today |
| `bench-runner` agent + `bench` skill: fixed method, NOT RUN instead of guesses, holdout never read, cost cap required for cloud profiles | 2026-10-13, conduit review | Bake-off harness exists (Phase 0) | Harness not built |
| `implementation-architect` agent (advisory plans, never edits) + soft 400 / hard 800 code-line limit per module, measured by a script | 2026-10-13, conduit review | First multi-module deliverable, or a module past 300 lines | No code yet |
| `security-reviewer` agent for the §21 threat model (sandbox flags, include fences, injection, secrets, egress); takes over the review gate for executor, docker and gateway paths | 2026-10-13, conduit review | WSL agent, executors or gateway code lands (Phase 0-1) | `architecture-guardian` covers the current surface |
| `integrity-auditor` agent (one area per call: code vs tests vs docs claims) + append-only audit log | 2026-10-13, conduit review | Phase 0 exit, then each phase exit | Little shipped code to audit |
| `license-reviewer` agent + stdlib `scripts/license_report.py` (importlib.metadata inventory, copyleft/unknown flags) | 2026-10-13, conduit review | Before the first public push (open decision 7) or the first new dependency | `update-deps` covers single packages |
| `testing` skill: layers, fakes, parallel-safe idioms, negative controls, `--collect-only` identity when re-marking tests | 2026-10-13, conduit review | First Phase 0 test modules | Nothing to cite yet |
| `cleanup` skill: worktrees, `~/.cache/barthelona/devcheck`, session-created docker objects, unreferenced code and config keys | 2026-10-13, conduit review | First docker/WSL debris (Phase 0) | No debris yet |
| ADR consistency test (README row = Status; `Amends` / `Amended by` pairs) + "a changed conclusion rewrites the headline" rule | 2026-10-13, conduit review | The owner starts accepting or superseding ADRs | All ADRs are Proposed |
| Explicit `.gitattributes`: LF per assembly extension, `binary` for objects and executables, `-text` for captured diagnostics | 2026-10-13, conduit review | Before the first diagnostics or binary fixture is committed | No fixtures yet |
| Registry-completeness test with a negative control, "stop rules" and a re-derive note in `add-node-type` / `add-dialect` | 2026-10-13, conduit review | First real node type or the NASM dialect adapter | Checklists not yet exercised |
| Generated `.codex/hooks.json` from `settings.json`, with hooks that parse `apply_patch` payloads and find the repo root without `CLAUDE_PROJECT_DIR` | 2026-10-13, conduit review | Codex edits code regularly; first log one real Codex payload | Codex hook payloads unverified |
| `guard-shell.ps1`: block `git add -A`/`.`/`--all`, `sudo` without `-n` inside `wsl`, and Python heredocs that write files | 2026-10-13, conduit review | Second occurrence of the prose rule being missed | Prose rule first |
| `dependency-steward` agent: batch survey of outdated locked packages (LangGraph trio, SDKs, oracle libs) and lock deltas | 2026-10-13, conduit review | Phase 1 start | Fresh locks |
| `scripts/health.py --line` for devlog entries (LOC, tests, instruction bytes, mirror and lock state, ADR counts) | 2026-10-13, conduit review | Phase 1 | Few numbers to trend |
| `pre-commit` config (ruff, mirror and lock checks) | 2026-10-13, second review | First collaborator or CI | Dropped from dev deps as unused |
| Guard `git -c alias.*=...push...` / configured push aliases, and anchor the template `.gitignore` build directories (`/build/`, `/lib/`) | 2026-10-13, review gate | First use of git aliases, or a source dir named `lib`/`build` | Low risk today |
