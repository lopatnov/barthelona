# Meterless engine prompts: catalogue and fit for Barthelona

Source: the 57 prompts on https://meterless.ai/engines.html (plus the "START HERE" prompt), saved unaltered in
[`prompts-verbatim.txt`](prompts-verbatim.txt) on 2026-10-23 (the whole page text: START HERE, all 57 prompts in page order, then the site's
hackathon and engine blurbs; checked: 57 entries, 8 Ideate, 10 Implement, 10 Combine, 12 Harden, 17 Power). Meterless is Apache-2.0; the engines are specs plus TypeScript reference
code, so every prompt that says "run the conformance suite" cannot be satisfied literally by Barthelona's Python ports
(see `docs/hackathon-demo.md`). We port the behaviour and test it with our own pytest suites.

Context for scoring: the Open Agent Hackathon MVP (deadline end of 2026-10-24) must show Meterless Nightshift + the
Markovian engine, NVIDIA Nemotron, more than one model, and (optionally) Zetaris. Barthelona generates assembly and the
assembler/linker/tests are the oracle. Done on main: Meterless provider, Markovian chunk loop, H-MEM recall/write-back,
plan/worker/review roles. In flight: PR #210 (injection guard).

**Fit score** is 0 to 5: how much the prompt strengthens the hackathon MVP per hour of work. 5 = do it now, 0 = irrelevant.
**Status**: Done, Partial, Next (do before the deadline), Later (after the hackathon), Skip.

## Top list

### Already done (or in review)

| Prompt | Category | State |
| --- | --- | --- |
| Memory plus long tasks | Combine | Done: `chunked run --memory`. Second-run-needs-fewer-chunks check is the open acceptance test. |
| Long tasks, flat context | Implement | Done in Python (`llm/markovian.py`); model-based carryover compression and conformance not ported. |
| Give my agent memory | Implement | Partial: `llm/hmem.py` without embeddings, dreaming, sleep, conflicts. |
| Add Meterless as a provider | Power | Done at L0/L1 (`llm/meterless.py`, `meterless status`); no Auto Detect or connect link. |
| Block prompt injection | Harden | PR #210 open; no precision/recall measurement yet. |

### Do next (ordered; each is under a few hours)

1. **A research agent that remembers** (Combine, 5). It is the demo's proof: run the same task twice with one memory file and
   print a chunks/tokens/time table. Cheap because the loop and memory exist.
2. **See every run in numbers** (Harden, 5). Per-chunk tokens, latency, outcome are already printed; persist them in
   `var/app.sqlite`, show the last ten runs and per-model stats. Also required by the demo rule (per-model statistics).
3. **Block prompt injection** (Harden, 5). Finish PR #210, then add a small labelled corpus and report precision/recall
   against the 0.95/0.90 targets. Judges look for safety evidence.
4. **Prove each test can fail** (Harden, 4). One deliberate break each for Markovian (drop carryover) and H-MEM (skip a
   write); confirm pytest fails; add a test for any miss. Strong quality evidence, cheap.
5. **Tell users the real reason** (Power, 4). Typed provider refusals reach the user with the server's message and fix;
   a refusal is never reported as a hardware limit; only transport failures fall back to another provider (invariant 11).
6. **Security review my integration** (Harden, 4). Threat-model table for tool calls, memory writes, untrusted content
   (web pages, Zetaris rows); fix the top three with tests. Mostly a document.
7. **Resume after a crash** (Harden, 4). Persist the last marker/carryover per chunk so a killed run resumes; matters for
   long NASM tasks on a laptop that overheats.
8. **Grade my provider integration** (Power, 3). Audit table (requirement, pass/fail, file, fix) against the L0-L2 levels;
   good for the write-up, fixes only the blockers.

### Skip for the MVP

All media and 3D prompts (images, speech, music, photo-to-3D, painting, sentence-to-3D, game/web/film export, 3D print,
best-3D-per-machine), Quick Connect, CRM accounts, media idempotency, and the "adopt without a rewrite" fetch wrapper.
Barthelona emits assembly text, not media.

## Catalogue

Categories: Ideate (prompt for any chat AI), Implement, Combine, Harden, Power (Meterless Runtime provider work).

### Start here

| # | Title | Engine | Summary | Fit | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | The one prompt | all | Read the repo, interview the user, recommend the first engine. | 1 | Skip (discovery is done) |

### Ideate (8)

| # | Title | Engine | Summary | Fit | Status / reason |
| --- | --- | --- | --- | --- | --- |
| 1 | Find my best use case | all | Interview, then five ideas ranked by effort and payoff. | 1 | Skip: use case chosen. |
| 2 | Weekend hackathon ideas | starter | Ten agent ideas, demo script for the top three. | 2 | Later: reuse the demo-script structure for the submission video. |
| 3 | Map it onto my product | all | Where each engine plugs in, what to skip. | 2 | Done informally in `docs/hackathon-demo.md`. |
| 4 | Explain it like I'm new | all | One analogy per engine. | 1 | Done: `meterless/meterless-explained.md`. |
| 5 | Estimate my token savings | Markovian | Cost model math for the user's workload. | 3 | Partial: `chunked run` already prints `standard_cost`, `markovian_cost`, `efficiency`; add to the write-up. |
| 6 | Pitch it to my team | all | One-page pilot brief under 400 words. | 3 | Next (writing only): adapt as the hackathon submission text. |
| 7 | Compare it to what I use | all | Honest side-by-side with current tools. | 2 | Later: compare to Qdrant memory and LangGraph. |
| 8 | Plan a 30-day rollout | all | One engine per week, gated by conformance. | 1 | Skip. |

### Implement (10)

| # | Title | Engine | Summary | Fit | Status / reason |
| --- | --- | --- | --- | --- | --- |
| 9 | Run the 90-second proof | H-MEM + Markovian | Run `memory-compounding-research` cold vs warm, no keys. | 2 | Skip: needs Node; our own two-run check replaces it. |
| 10 | Scaffold a working agent | starter | `degit` the agentathon starter and adapt it. | 1 | Skip: Barthelona is the agent; TypeScript starter does not fit. |
| 11 | Give my agent memory | H-MEM | Implement H-MEM until conformance passes. | 5 | Partial/Done (Python port, no conformance). |
| 12 | Long tasks, flat context | Markovian | Chunked loop with measured before/after. | 5 | Done (Python port). |
| 13 | Keep parallel agents in sync | World Model | Event-sourced shared state for parallel agents. | 2 | Later: matches sprint-level parallelism in Phase 2+. |
| 14 | Route tools by intent | Scout | Intent detection before model calls, eval harness. | 3 | Later: Barthelona already routes by role chains. |
| 15 | Let memory sleep on it | H-MEM | Preview-first consolidation (merge/prune proposals). | 2 | Later: needs a large memory store first. |
| 16 | Mine memory from chats | H-MEM | Records from transcripts/docs with source and confidence. | 3 | Later: feeds opt-in training data (D-036) and Zetaris rows. |
| 17 | Sign every tool call | Scout | Execution contracts; no tool runs without one. | 3 | Later: aligns with invariant 2 and the sandbox; larger design. |
| 18 | Ingest once, never twice | World Model | Stable IDs, re-ingest gives an empty diff. | 3 | Later: relevant if Zetaris rows are ingested (idempotent upsert). |

### Combine (10)

| # | Title | Engine | Summary | Fit | Status / reason |
| --- | --- | --- | --- | --- | --- |
| 19 | Memory plus long tasks | H-MEM + Markovian | Recall per chunk, write back, second run needs fewer chunks. | 5 | Done; acceptance measurement open (see top list 1). |
| 20 | Check memory before acting | Scout + H-MEM | Query memory before each classified intent. | 2 | Later. |
| 21 | Route long jobs to Markovian | Scout + Markovian | Short work fast path, long work chunked. | 3 | Later: today `chunked run` is explicit; auto routing is a small follow-up. |
| 22 | World state into memory | World Model + H-MEM | Durable memory records linked by entity ID. | 2 | Later. |
| 23 | Plan from the world model | Scout + World Model | Query exactly the needed entities before planning. | 2 | Later. |
| 24 | Many drafts, one shared state | World Model + Markovian | Parallel drafts on one state. | 2 | Later. |
| 25 | The full stack in one agent | all four | One agent using all engines, with a data-flow diagram. | 2 | Later: two of four engines is the honest MVP claim. |
| 26 | Upgrade the hackathon starter | Scout + Markovian | Starter plus intent guard and chunked tasks. | 1 | Skip (TypeScript starter). |
| 27 | A research agent that remembers | Markovian + H-MEM | Same question twice, table of chunks/tokens/time. | 5 | Next (top list 1). |
| 28 | Accounts that remember people | World Model + H-MEM | CRM with learned preferences. | 0 | Skip. |

### Harden (12)

| # | Title | Engine | Summary | Fit | Status / reason |
| --- | --- | --- | --- | --- | --- |
| 29 | Block prompt injection | Scout | Guard untrusted input, report precision/recall. | 5 | In review (#210); measurement next. |
| 30 | Grow the eval set from real traffic | Scout | Capture real requests as regression cases. | 2 | Later: after the injection corpus exists. |
| 31 | Settle conflicting memories | H-MEM | Conflict resolution with recorded reasons. | 3 | Later: not ported; needed once several models write memory. |
| 32 | Add a trust ledger | H-MEM | Source/confidence per write, reads logged, low trust cannot overwrite. | 3 | Partial: append-only ledger exists; trust-priority overwrite rule missing. |
| 33 | Audit memory for privacy | H-MEM | Find network calls carrying memory, undeletable data. | 3 | Later: memory is a local sqlite file; cheap test that it never leaves the machine. |
| 34 | Survive concurrent writers | World Model | Ten writers, no lost updates. | 0 | Skip (no World Model). |
| 35 | Prove each test can fail | all | Deliberate breaks per engine, tests must fail. | 4 | Next (top list 4). |
| 36 | See every run in numbers | Markovian | Per-chunk telemetry, run history, alert thresholds. | 5 | Next (top list 2). |
| 37 | Tune chunk sizes on your work | Markovian | Sweep four chunk sizes on three tasks. | 3 | Next if time: also yields "winner config" evidence; costs model calls. |
| 38 | Resume after a crash | Markovian | Kill mid-chunk, resume from last marker. | 4 | Next (top list 7). |
| 39 | Security review my integration | Scout | Threat-model table, fix top three. | 4 | Next (top list 6). |
| 40 | Gate every change in CI | all | Run conformance and evals on each PR. | 2 | Partial: CI already runs ruff, mypy, pytest. |

### Power: Meterless Runtime provider (17)

| # | Title | Summary | Fit | Status / reason |
| --- | --- | --- | --- | --- |
| 41 | Add Meterless as a provider | Contract v4: base URL normalise, bearer token, `meterless-app`, routing-mode ids, health via `/v1/models`, Auto Detect. | 5 | Done at L0/L1; Auto Detect and URL normalisation could be checked. |
| 42 | Route each task to the right mode | Pure `planRoute` task to class.disposition. | 2 | Later: our role chains already map role to `meterless/<mode>`. |
| 43 | Show what this machine can serve | Live class state, one health event. | 2 | Later: `meterless status` covers the basics. |
| 44 | Read every answer it sends | Handle JSON/SSE/media answer shapes, retries 2/4/8 s. | 3 | Partial: text only; 429 backoff worth verifying. |
| 45 | Make images, speech and music | Media via the jobs plane. | 0 | Skip. |
| 46 | Never render the same thing twice | Idempotent media makes. | 0 | Skip. |
| 47 | Tell users the real reason | Server message first, fix wins, refusal not blamed on hardware. | 4 | Next (top list 5). |
| 48 | Adopt it without a rewrite | `fetch` interceptor for hard-coded OpenAI calls. | 0 | Skip (browser pattern). |
| 49 | Grade my provider integration | Audit by level L0..L3 and Quick Connect. | 3 | Next if time (top list 8). |
| 50 | Connect with one paste or one scan | Parse `/connect#k=` links. | 1 | Skip; note the key-in-fragment, never-log rule for any future link. |
| 51 | Turn a photo into a 3D model | `/v1/meterless/3d`. | 0 | Skip. |
| 52 | Paint any 3D model with PBR | Texture lane. | 0 | Skip. |
| 53 | From a sentence to a 3D model | Still then lift. | 0 | Skip. |
| 54 | Ship game, web or film-ready 3D | Finish profiles. | 0 | Skip. |
| 55 | Print what you made | 3MF/STL export. | 0 | Skip. |
| 56 | Always get this machine's best 3D | Adaptive 3D menu. | 0 | Skip. |
| 57 | Build the whole provider from one spec | Implement the v5 provider PRD with acceptance checklist. | 2 | Later: the spec file is not in the project; useful as a post-hackathon audit. |

## Notes

- The prompts name paths in the Meterless repo (`engines/<engine>/AGENTS.md`, `docs/`, `examples/`). Fetch them from
  https://github.com/Meterless/Meterless when implementing; the sandbox cannot reach meterless.ai itself.
- Prompt numbering here is this catalogue's own (page order, top to bottom); the page has no numbers.
- Re-score after the hackathon: the Later rows with fit 3 (Scout routing, conflict resolution, trust-priority ledger,
  mining, idempotent ingest) are the natural Phase 2 follow-ups.
