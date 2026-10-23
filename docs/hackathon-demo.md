# Open Agent Hackathon 2026: Meterless + Nemotron demo

What Barthelona uses from the hackathon stack, and how to reproduce the demo.

| Layer | Used for | Where |
| --- | --- | --- |
| Meterless Nightshift (Power) | Primary provider for the `meterless` profile | `config/models.yaml` (`meterless` provider), `src/barthelona/llm/meterless.py` |
| NVIDIA Nemotron (Power) | Model behind a Nightshift lane, key lives in Nightshift only | Nightshift Providers tab |
| Markovian Engine (Build) | Long generation as bounded chunks with flat context | `src/barthelona/llm/markovian.py`, `barthelona chunked run` |
| Zetaris (Data) | Planned: structured knowledge store next to Qdrant | not built yet |

The Markovian code is a Python port of the Apache-2.0 spec at github.com/Meterless/Meterless/tree/main/engines/markovian
(ARCHITECT mode). Not ported: model-based carryover compression, RESEARCH mode, the reflection pass. The TypeScript
conformance suite cannot run against a Python port; `tests/unit/llm/test_markovian.py` covers the spec formulas
(standard vs Markovian cost, efficiency), the marker protocol, the 24-character state minimum and the chunk bounds.

## Memory plus long tasks (H-MEM into Markovian)

`src/barthelona/llm/hmem.py` is a small Python port of the H-MEM spec (github.com/Meterless/Meterless, `engines/hmem`).
`chunked run --memory var/hmem.sqlite` recalls what earlier runs learned and puts it in front of chunk 1 only (the
spec's rule: later chunks get the carryover, so the prompt stays flat), then writes the DECISIONS and CONTEXT lines of
every chunk's state block back with source `markovian:<run>` and an append-only ledger. Not ported: embeddings (the
semantic weight 0.35 is dropped and the other six renormalised), dreaming, sleep cycle, conflict resolution. The
conformance suites are TypeScript and cannot run against the port; `tests/unit/llm/test_hmem.py` covers the
recall-into-chunk-0, write-back and reinforcement behaviours.

Several models in one run: `--plan-role planner` asks the planner chain (`meterless/deep`) for a short plan that is
added to the task, the chunks run on the `worker` chain (`meterless/auto`), and `--review-role cheap` asks the cheap
chain (`meterless/fast`) for an advisory review (the assembler stays the oracle). Which concrete model answers each
routing class is decided by the lanes in Nightshift; the run prints `served_by` for the plan, every chunk and the
review. Use at least two different model families in the lanes to show it.

Compounding check: run the same task twice with the same `--memory` file and compare `chunks=` in the two summaries.
A shorter second run only counts if the output is valid, so add `--assemble`: the code is assembled with NASM
(`nasm -f elf64`, never linked or run) and the run is green only if it assembles. `--repair N` gives the model NASM's
errors back for up to N more attempts. If `nasm` is not on PATH, pass `--nasm <path>` or set `BARTHELONA_NASM`; an unavailable assembler is reported as `unavailable`, never as a pass. Memory is written only for runs that assemble; a rejected output teaches
nothing. First live data (2026-10-23, hello world): run 1 took 9 chunks, run 2 took 1 chunk, but run 2's file contained
the program twice and NASM rejected it (`label msg inconsistently redefined`); `extract_code` now drops a repeated block.

## Tests that can fail (Meterless prompt "Prove each test can fail")

One deliberate break each, run on 2026-10-23, then reverted with `git checkout`. Every break made pytest fail (no break was missed):

| Break | Caught by |
| --- | --- |
| Server `fix[]` dropped from the error text | `test_the_server_message_comes_first_and_its_fix_wins_over_our_hint` |
| Carrier refusal given our own hint | `test_a_carrier_refusal_is_never_blamed_on_the_machine_or_given_our_hint` |
| `extract_code` keeps a repeated program | `test_extract_code_drops_a_block_that_repeats_the_program_without_its_comments` |
| H-MEM written although the oracle rejected the run | `test_assemble_failure_exits_non_zero_and_keeps_the_memory_clean` |
| `%include` guard switched off | `test_directives_that_read_host_files_are_refused_without_running_nasm` |
| Markovian carryover dropped (state block ignored) | `test_chunks_run_until_the_model_completes` |
| H-MEM write skipped (rolled back) | `test_memory_refuses_to_store_a_blocked_fact_and_ledgers_the_rejection` |
| Injection rule weakened (`ignore/disregard` no longer matches) | `test_known_injections_are_blocked_with_evidence` (the `disregard` case) |

## Reproduce

1. In Nightshift: Setup, Providers, add the NVIDIA key; NIGHT, LANES, add a Nemotron lane (for example
   `nvidia/nemotron-3.5-lightning-30b-a3b`) and pin it.
2. Put the Console values in `.env` (gitignored): `METERLESS_RUNTIME_TOKEN`, and `METERLESS_BASE_URL` if it is not
   `http://127.0.0.1:8088/v1`. The NVIDIA key never goes into `.env`.
3. Check the runtime: `python -m barthelona meterless status` prints `online` and the `meterless/*` ids, or
   `unauthorized` for a wrong token, or `offline`.
4. Run a long task through the chunk loop:
   `python -m barthelona chunked run @task.txt --profile meterless --out result.txt`
   It prints one row per chunk (tokens in and out, latency, serving model, marker, carryover source) and a summary
   with `peak_prompt` (stays flat), `standard_cost`, `markovian_cost` and `efficiency`.
   For the memory proof use `--assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite`, run it twice,
   then `python -m barthelona chunked stats`.
5. In Nightshift's run details, confirm the Nemotron lane served the chunks.

## Honest limits

- Without a Nightshift token the router skips `meterless` and falls to the local model; the run still works.
- `meterless/auto` may route to a non-NVIDIA model; pin the Nemotron lane to make the evidence unambiguous.
- Token counts are `measured` when the provider reports usage, otherwise `estimated` as ceil(chars/4).
