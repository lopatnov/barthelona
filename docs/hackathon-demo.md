# Open Agent Hackathon 2026: Meterless + Nemotron demo

What Barthelona uses from the hackathon stack, and how to reproduce the demo.

| Layer | Used for | Where |
| --- | --- | --- |
| Meterless Nightshift (Power) | Primary provider for the `meterless` profile | `config/models.yaml` (`meterless` provider), `src/barthelona/llm/meterless.py` |
| NVIDIA Nemotron (Power) | Model behind a Nightshift lane, key lives in Nightshift only | Nightshift Providers tab |
| Markovian Engine (Build) | Long generation as bounded chunks with flat context | `src/barthelona/llm/markovian.py`, `barthelona chunked run` |
| Zetaris (Data) | Optional structured knowledge store next to Qdrant: read-only SQL, rows enter chunk 1 as untrusted facts | `src/barthelona/llm/zetaris.py`, `barthelona zetaris`, `chunked run --facts-sql` |

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
errors back for up to N more attempts; `--repair-role planner` runs those attempts on the deeper chain
(`meterless/deep`). NASM is found via `--nasm`, `BARTHELONA_NASM`, `NASM_PATH` (a file or its folder), PATH, then the usual Windows install folders; an unavailable assembler is reported as `unavailable`, never as a pass. Memory is written only for runs that assemble; a rejected output teaches
nothing. First live data (2026-10-23, hello world): run 1 took 9 chunks, run 2 took 1 chunk, but run 2's file contained
the program twice and NASM rejected it (`label msg inconsistently redefined`); `extract_code` now drops a repeated block.

The completing chunk is asked to write DECISIONS and CONTEXT lines under `[TASK_COMPLETE]`, and memory keeps them, so a
run that finishes in one chunk still teaches the next one (#214). With one chunk the Markovian cost model cannot beat
the standard one, so the summary prints `efficiency=too short to compare` instead of `0.0%`. Not done from #214: storing
what the assembler or the emulator rejected as a lesson.

## Zetaris facts (optional)

Zetaris must be running (the hackathon guide, Data part 1.9) and its API key created by you in the Zetaris web
interface. Put `ZETARIS_API_KEY` (and `ZETARIS_REST_URL`, `ZETARIS_ORG_ID` if they differ from
`http://localhost:8888/api/v1.0` and `1`) in `.env`. Then:

- `python -m barthelona zetaris status` runs `SELECT 1` and prints `online`, `unauthorized`, `offline` or `unconfigured`.
- `python -m barthelona zetaris sql "SHOW LIGHTNING DATABASES"` prints the rows. Only one SELECT, SHOW, DESCRIBE or
  WITH statement is ever sent.
- `chunked run ... --facts-sql "SELECT name, nr FROM <your table>"` puts the rows in front of chunk 1 inside an
  untrusted-data block (the injection guard can refuse them). A missing key or a failing Zetaris stops the run; it is
  never skipped silently.

The request follows the guide (`POST /sql-editor/sqls/run`, bearer key, `X-Org-ID`, `X-Request-ID`). It was tested
against a fake HTTP transport only: it has not run against a real Zetaris yet. Registering a table of assembler
facts (for example Linux x86-64 syscall numbers) in Zetaris is still manual.

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
   `python -m barthelona chunked run @task.txt --profile meterless --out result.txt` (keep generated files in a folder
   under `demos/`, never in the repository root; the memory proof lives in `demos/hello/`)
   It prints one row per chunk (tokens in and out, latency, serving model, marker, carryover source) and a summary
   with `peak_prompt` (stays flat), `standard_cost`, `markovian_cost` and `efficiency`.
   For the memory proof use the full command in `demos/hello/README.md` (it already has `--assemble --repair 2`,
   `--expect-stdout`/`--expect-exit` for the emulator check, `--memory` and `--stats`), run it twice, then `python -m barthelona chunked stats`.
5. In Nightshift's run details, confirm the Nemotron lane served the chunks.

## Honest limits

- Without a Nightshift token the router skips `meterless` and falls to the local model; the run still works.
- `meterless/auto` may route to a non-NVIDIA model; pin the Nemotron lane to make the evidence unambiguous.
- Token counts are `measured` when the provider reports usage, otherwise `estimated` as ceil(chars/4).
