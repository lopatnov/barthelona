# Zetaris Integration Guide

Complete step-by-step guide to setting up and using Zetaris as a structured knowledge store for Barthelona.

---

## Table of Contents

1. [What is Zetaris?](#what-is-zetaris)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Zetaris Setup](#zetaris-setup)
5. [Barthelona Configuration](#barthelona-configuration)
6. [Verification](#verification)
7. [Using Zetaris with `chunked run`](#using-zetaris-with-chunked-run)
8. [Registering Assembler Facts in Zetaris](#registering-assembler-facts-in-zetaris)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Usage](#advanced-usage)
11. [References](#references)

---

## What is Zetaris?

**Zetaris** is a data virtualization platform that provides a unified SQL interface over multiple data sources. Barthelona uses it as a **structured knowledge store** (a hackathon requirement; the engine itself also runs without it) — a place to keep queryable facts (syscall numbers, instruction forms, ABI rules, etc.) that can be injected into the first chunk of a `chunked run` as untrusted context.

Key points:

- **Read-only for queries**: `zetaris sql` and `--facts-sql` send `SELECT`/`SHOW`/`DESCRIBE`/`WITH` only; the only commands that write are `zetaris publish` (run data) and the one-time table registration
- **Opt-in** — runs work fine without it
- **Untrusted data** — rows are wrapped in `[ZETARIS FACTS]` block and subject to injection guard
- **Complements Qdrant** — Zetaris = exact SQL facts; Qdrant = vector search over docs

---

## Prerequisites

| Requirement          | Details                                                                           |
| -------------------- | --------------------------------------------------------------------------------- |
| **Zetaris Instance** | Running locally or remotely (Docker, 8 GB RAM recommended)                        |
| **API Key**          | Created in Zetaris web interface                                                  |
| **Network Access**   | Barthelona must reach Zetaris REST API (default `http://localhost:8888/api/v1.0`) |
| **Docker**           | For running Zetaris locally (see Installation)                                    |

---

## Installation

### Option A: Docker (Recommended for Local Development)

```bash
# Pull and run Zetaris (adjust version as needed)
docker run -d \
  --name zetaris \
  -p 8888:8888 \
  -e ZETARIS_LICENSE=<your-license> \
  zetaris/zetaris:latest
```

> **Note**: Zetaris requires a license. For hackathon/demo purposes, follow the [Open Agent Hackathon 2026 guide](https://github.com/Meterless/Meterless) which includes Zetaris setup.

### Option B: Existing Zetaris Instance

If you have access to a hosted Zetaris instance, note its REST URL and proceed to configuration.

---

## Zetaris Setup

### 1. Create API Key

1. Log into Zetaris web interface
2. Navigate to **Settings → API Keys** (or similar)
3. Generate a new API key
4. Copy it — you won't see it again

### 2. Note Connection Details

| Variable           | Default                          | Your Value |
| ------------------ | -------------------------------- | ---------- |
| `ZETARIS_REST_URL` | `http://localhost:8888/api/v1.0` |            |
| `ZETARIS_ORG_ID`   | `1`                              |            |
| `ZETARIS_API_KEY`  | _(required)_                     |            |

### 3. Verify Zetaris is Accessible

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "X-Org-ID: 1" \
     http://localhost:8888/api/v1.0/sql-editor/sqls/run \
     -d '{"sql": "SELECT 1"}'
```

Should return a successful response with `rows: [[1]]`.

---

## Barthelona Configuration

Add to your `.env` file (create from `.env.example` if needed):

```bash
# .env (gitignored — never commit!)
ZETARIS_API_KEY=your-api-key-here
# Optional, only if different from defaults:
# ZETARIS_REST_URL=http://localhost:8888/api/v1.0
# ZETARIS_ORG_ID=1
```

No changes needed to `config/models.yaml` — Zetaris is not a model provider.

---

## Verification

### Check Connection Status

```bash
python -m barthelona zetaris status
```

**Expected output:**

```
Zetaris status: online
```

**Possible responses:**
| Status | Meaning |
|--------|---------|
| `online` | ✅ Connected, `SELECT 1` succeeded |
| `unauthorized` | ❌ Invalid/missing `ZETARIS_API_KEY` |
| `offline` | ❌ Zetaris unreachable (check URL, network, Docker) |
| `unconfigured` | ❌ `ZETARIS_API_KEY` not set in environment |

### Run a Test Query

```bash
# List databases (example)
python -m barthelona zetaris sql "SHOW LIGHTNING DATABASES"

# Query a knowledge table (registered as in the section below)
python -m barthelona zetaris sql "SELECT number, name, arg1 FROM barthelona_files.linux_x64_syscalls LIMIT 10"

# With limit
python -m barthelona zetaris sql --limit 100 "WITH cte AS (...) SELECT * FROM cte"
```

**Constraints:**

- Only **one** statement per call (`SELECT`, `SHOW`, `DESCRIBE`, or `WITH`)
- `zetaris sql` is read-only (it refuses `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`); writing goes only through `zetaris publish` and the registration statements
- Results returned as text table

---

## Using Zetaris with `chunked run`

Inject Zetaris facts into the first chunk of a long task:

```bash
python -m barthelona chunked run "Write a NASM program that prints Hello using the write syscall" \
  --profile meterless \
  --role worker \
  --assemble --repair 2 \
  --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'" \
  --memory var/hmem.sqlite \
  --stats var/runs.sqlite \
  --out myprog.asm
```

### How It Works

1. **Before chunk 1**: Barthelona executes the `--facts-sql` query against Zetaris
2. **Rows returned** → formatted as text table
3. **Injected** into chunk 1's prompt as an untrusted block: a `[ZETARIS FACTS] rows of: <your query>` line followed by
   the rows (`cell | cell | ...`, one row per line) wrapped as untrusted data, for example
   `write | rdi=fd | rsi=buf | rdx=count`
4. **Injection guard** validates the block (refuses prompt injection attempts)
5. **Model sees facts** and can use them in generation
6. **Oracle decides** — assembler/emulator still validate correctness

### Query Design Tips

| Tip                          | Example                                                 |
| ---------------------------- | ------------------------------------------------------- |
| Filter to relevant facts     | `WHERE topic = 'nasm' AND arch = 'x86-64'`              |
| Limit rows                   | `LIMIT 20` (prevents context overflow)                  |
| Select only needed columns   | `SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls` |
| Use CTEs for complex queries | `WITH filtered AS (...) SELECT * FROM filtered`         |

---

## Registering Assembler Facts in Zetaris

> **Current state (2026-10-24):** the facts are two **file tables** registered by hand from CSV files; there is no
> automated ingestion pipeline. The earlier version of this section proposed `CREATE TABLE` and `INSERT` statements
> for `syscalls`, `instructions` and `directives` tables; that was never run and is not how the tables on the dev
> PC were made. Instruction forms and directives are **not** in Zetaris yet.

What exists (verified on the local hackathon stack, build 2.4.3):

| Table                                | Rows | Source file                                |
| ------------------------------------ | ---: | ------------------------------------------ |
| `barthelona_files.linux_x64_syscalls` |   37 | `knowledge/zetaris/linux_x64_syscalls.csv` |
| `barthelona_files.abi_facts`          |   11 | `knowledge/zetaris/abi_facts.csv`          |

### Registration steps

The exact commands (copy the CSVs into the volume that the Zetaris api and driver containers share, with relative
paths because an absolute `C:\` path breaks `docker cp`; then `CREATE LIGHTNING DATABASE` and
`CREATE LIGHTNING FILESTORE TABLE ... FORMAT CSV OPTIONS (path "...", header "true", delimiter ",")`) are in
[`knowledge/zetaris/README.md`](../knowledge/zetaris/README.md) and in section 1.3 of
[`hackathon-demo-guide.md`](hackathon-demo-guide.md). The path in the `OPTIONS` is a path **inside the Zetaris
containers** (`/home/zetaris/customer-data/shared/barthelona/...`), not a Windows path. The API key was accepted for
`CREATE` over the REST endpoint; each statement is sent on its own, and a repeated `CREATE` answers "already exists".
The numbers in the CSVs were written from memory of the public syscall table and still need checking against the kernel
table (`syscall_64.tbl`) and the System V psABI.

### What writes to Zetaris

`zetaris sql` and `--facts-sql` send only one `SELECT`, `SHOW`, `DESCRIBE` or `WITH`. The only commands that write are
`zetaris publish`, which registers and fills the `barthelona_runtime` tables (`runs`, `run_chunks`, `memories`,
`memory_ledger`) from the local SQLite files, and the registration statements above, which an administrator sends
once. `zetaris seed` reads Zetaris and writes only the local H-MEM file.

### Not built

- No ingestion pipeline (`knowledge/sources.yaml` as a Zetaris source: planned, roadmap Phase 3).
- No instruction-form, directive or diagnostic tables; no manuals loaded (Zetaris can register PDF, text and markdown
  files as tables, which nobody has tried for `asm_doc/`).

---

---

## Troubleshooting

### `zetaris status` says `unauthorized`

| Cause                   | Fix                                                            |
| ----------------------- | -------------------------------------------------------------- |
| Wrong `ZETARIS_API_KEY` | Re-copy from Zetaris web UI; ensure no extra spaces            |
| Key expired/regenerated | Generate new key in Zetaris; update `.env`                     |
| `.env` not loaded       | Use `. .\scripts\activate.ps1` or `source scripts/activate.sh` |

### `zetaris status` says `offline`

| Cause                         | Fix                                                              |
| ----------------------------- | ---------------------------------------------------------------- |
| Zetaris container not running | `docker start zetaris`                                           |
| Wrong `ZETARIS_REST_URL`      | Check URL in `.env`; default is `http://localhost:8888/api/v1.0` |
| Network/firewall              | Ensure port 8888 accessible; try `curl` test above               |

### `zetaris status` says `unconfigured`

| Cause                     | Fix                            |
| ------------------------- | ------------------------------ |
| `ZETARIS_API_KEY` not set | Add to `.env` and reload shell |

### Query fails / returns error

| Cause                     | Fix                                                      |
| ------------------------- | -------------------------------------------------------- |
| Multiple statements       | Only one `SELECT`/`SHOW`/`DESCRIBE`/`WITH` allowed       |
| Write operation attempted | `zetaris sql` is read-only; use `zetaris publish` or the registration steps |
| Table doesn't exist       | Check spelling; use `SHOW TABLES` to list                |
| Org ID wrong              | Set correct `ZETARIS_ORG_ID` in `.env`                   |

### `--facts-sql` doesn't seem to affect output

| Cause                      | Fix                                                 |
| -------------------------- | --------------------------------------------------- |
| Query returned no rows     | Test query manually with `zetaris sql` first        |
| Injection guard blocked it | Check logs for `injection_blocked`; simplify query  |
| Model ignored facts        | Facts are untrusted context; model may not use them |

---

## Advanced Usage

### Combining Zetaris + H-MEM

```bash
# Zetaris provides external facts; H-MEM provides learned facts from prior runs
python -m barthelona chunked run "Complex NASM task" \
  --profile meterless \
  --facts-sql "SELECT * FROM nasm_instructions WHERE mnemonic IN ('mov', 'lea', 'call')" \
  --memory var/hmem.sqlite \
  --assemble --repair 2 \
  --expect-stdout "..." --expect-exit 0 \
  --out complex.asm
```

**Order in chunk 1 prompt:**

1. Role + output format
2. Dialect rule card
3. Project card (target/ABI)
4. Contracts
5. **Zetaris facts** (external, untrusted)
6. **H-MEM facts** (learned, trusted)
7. Doc chunks
8. Code context
9. Task + errors

### Using with Different Profiles

```bash
# Works with any profile that uses a model
--profile meterless --facts-sql "..."  # Nightshift
--profile hybrid --facts-sql "..."     # Anthropic/OpenAI/etc.
--profile local-only --facts-sql "..." # LM Studio only
```

### Programmatic Access (Python)

```python
from barthelona.llm.zetaris import ZetarisClient

client = ZetarisClient()  # reads env vars automatically
rows = client.query("SELECT name, number FROM barthelona_files.linux_x64_syscalls LIMIT 10")
for row in rows:
    print(row)
```

---

## References

| Document                       | Link                                                                                                      |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Quickstart (includes Zetaris)  | [`docs/quickstart.md`](quickstart.md)                                                                     |
| Commands (zetaris)             | [`docs/quickstart.md`](quickstart.md#25-zetaris-status-sql-seed-publish)  |
| Runbook (environment setup)    | [`docs/runbook.md`](runbook.md#4-optional)                                                                |
| Hackathon Demo Notes           | [`docs/hackathon-demo.md`](hackathon-demo.md#zetaris-facts)                                      |
| Architecture (Knowledge Layer) | [`docs/architecture.md`](architecture.md#14-knowledge-layer)                                              |
| ADR D-016                      | [Knowledge: exact facts and FTS5 first, Qdrant](adr/D-016-knowledge-exact-facts-and-fts5-first-qdrant.md) |
| ADR D-034                      | [Project-owned Qdrant in docker-compose](adr/D-034-project-owned-qdrant-in-docker-compose.md)             |

---

## Quick Reference Card

```bash
# 1. Start Zetaris (Docker)
docker run -d --name zetaris -p 8888:8888 zetaris/zetaris:latest

# 2. Create API key in Zetaris web UI

# 3. Add to .env
ZETARIS_API_KEY=your-key
# ZETARIS_REST_URL=http://localhost:8888/api/v1.0  # default
# ZETARIS_ORG_ID=1                                 # default

# 4. Verify
python -m barthelona zetaris status
# → should print: Zetaris status: online

# 5. Test query
python -m barthelona zetaris sql "SHOW TABLES"

# 6. Use in chunked run
python -m barthelona chunked run "Write a NASM program that prints Hello using the write syscall" \
  --profile meterless \
  --facts-sql "SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name = 'write'" \
  --assemble --repair 2 \
  --out write_wrapper.asm
```

---

## Known Limitations (2026-10-24)

| Limitation                              | Status                                 |
| --------------------------------------- | -------------------------------------- |
| No automated fact ingestion pipeline    | Manual file-table registration (Phase 3) |
| Validated against a real Zetaris        | Yes, local hackathon build 2.4.3, 2026-10-24 (status, sql, seed, publish) |
| Single-statement restriction            | By design (safety)                     |
| Read-only queries (`zetaris sql`)       | By design (safety); writes only via `publish` and registration |
| No demo project using `--facts-sql`     | Planned; the create flow uses the tables by default |

---

_Last updated: 2026-10-24. For the latest, check `docs/quickstart.md` and `docs/hackathon-demo.md`._
