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
5. In Nightshift's run details, confirm the Nemotron lane served the chunks.

## Honest limits

- Without a Nightshift token the router skips `meterless` and falls to the local model; the run still works.
- `meterless/auto` may route to a non-NVIDIA model; pin the Nemotron lane to make the evidence unambiguous.
- Token counts are `measured` when the provider reports usage, otherwise `estimated` as ceil(chars/4).
