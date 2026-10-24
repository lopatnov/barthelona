# Zetaris and the Meterless engines

Zetaris is the data layer under the four engines: it holds knowledge the engines read and the run data they
produce, and SQLite stays the engine's own store (invariant 8). Status: **done** is in PR #247, **next** is not built.

| Engine | Zetaris reads (knowledge in) | Zetaris receives (data out) | Status |
| --- | --- | --- | --- |
| H-MEM (memory) | `zetaris seed` mines the registered tables into long-term memories. Source `zetaris:<table>`, confidence 0.9, so the trust ledger shows where each fact came from and a re-seed reinforces instead of duplicating. A run recalls only the top facts for its task, not a fixed dump. | `zetaris publish` exports `memories` and `memory_ledger`: memory growth and provenance are SQL-queryable. | seed and publish done |
| Markovian (long tasks) | Chunk 0 gets recalled facts (above) or `--facts-sql` rows; every later chunk gets a fresh H-MEM recall for the state so far (`chunked run --memory`). | `runs` and `run_chunks` (tokens, latency, markers, fallbacks) are published, so "second run needs fewer chunks" is one SELECT. | done (per-chunk recall) |
| Scout Intent (route and guard) | Next: before a risky step, query the ABI and syscall tables (is this syscall known, which registers) and put the answer in the execution contract. | Next: intent and verdict per request, to grow the eval set from real traffic. | next |
| World Model (shared state) | Next: entities (syscall, ABI rule, requirement, test) get stable IDs derived from the table keys, so re-ingest gives an empty diff. | Next: spec, tests and run entities, so parallel drafts plan from the same facts. | next |

Why this order: seeding and publishing need no new engine code, only the data path, and they make the hackathon
proof visible (first run warm from Zetaris, second run cheaper, both queryable in Zetaris).

Try it (Zetaris running, `ZETARIS_API_KEY` set, tables registered per `knowledge/zetaris/README.md`):

```
python -m barthelona zetaris seed --memory var/hmem.sqlite
python -m barthelona chunked run ... --memory var/hmem.sqlite --stats var/runs.sqlite
python -m barthelona zetaris publish <driver container>
```
