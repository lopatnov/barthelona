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

- **Read-only** from Barthelona's perspective (`SELECT`/`SHOW`/`DESCRIBE`/`WITH` only)
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

# Query a table (replace with your table)
python -m barthelona zetaris sql "SELECT name, nr FROM syscalls LIMIT 10"

# With limit
python -m barthelona zetaris sql --limit 100 "WITH cte AS (...) SELECT * FROM cte"
```

**Constraints:**

- Only **one** statement per call (`SELECT`, `SHOW`, `DESCRIBE`, or `WITH`)
- Read-only — no `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`
- Results returned as text table

---

## Using Zetaris with `chunked run`

Inject Zetaris facts into the first chunk of a long task:

```bash
python -m barthelona chunked run "Write a NASM program that uses sys_write" \
  --profile meterless \
  --role worker \
  --assemble --repair 2 \
  --facts-sql "SELECT name, nr, args FROM syscalls WHERE name LIKE 'sys_write%'" \
  --memory var/hmem.sqlite \
  --stats var/runs.sqlite \
  --out myprog.asm
```

### How It Works

1. **Before chunk 1**: Barthelona executes the `--facts-sql` query against Zetaris
2. **Rows returned** → formatted as text table
3. **Injected** into chunk 1's prompt as an untrusted block:
   ```
   [ZETARIS FACTS]
   name    | nr | args
   --------|----|-----
   sys_write | 1 | fd, buf, count
   [/ZETARIS FACTS]
   ```
4. **Injection guard** validates the block (refuses prompt injection attempts)
5. **Model sees facts** and can use them in generation
6. **Oracle decides** — assembler/emulator still validate correctness

### Query Design Tips

| Tip                          | Example                                                 |
| ---------------------------- | ------------------------------------------------------- |
| Filter to relevant facts     | `WHERE topic = 'nasm' AND arch = 'x86-64'`              |
| Limit rows                   | `LIMIT 20` (prevents context overflow)                  |
| Select only needed columns   | `SELECT mnemonic, operands, encoding FROM instructions` |
| Use CTEs for complex queries | `WITH filtered AS (...) SELECT * FROM filtered`         |

---

## Registering Assembler Facts in Zetaris

> ⚠️ **Current State**: Registering tables in Zetaris is **manual**. There is no automated ingestion pipeline yet. This section documents the intended workflow.

### Intended Schema for Assembly Facts

```sql
-- Syscalls table
CREATE TABLE syscalls (
    name VARCHAR(64) PRIMARY KEY,    -- e.g., 'sys_write'
    nr INTEGER NOT NULL,             -- syscall number (1 for write)
    args VARCHAR(256),               -- comma-separated: 'fd, buf, count'
    arch VARCHAR(16),                -- 'x86-64', 'aarch64'
    abi VARCHAR(16)                  -- 'sysv64', 'win64'
);

-- Instructions table
CREATE TABLE instructions (
    mnemonic VARCHAR(32),
    operands VARCHAR(128),
    encoding VARCHAR(64),            -- e.g., '48 89 C7'
    cpu_flags VARCHAR(64),           -- affected flags
    isa_ext VARCHAR(32),             -- 'BASE', 'AVX2', 'AVX512'
    dialect VARCHAR(16),             -- 'nasm', 'gas-intel', 'gas-att'
    arch VARCHAR(16)
);

-- Directives table
CREATE TABLE directives (
    name VARCHAR(64),
    dialect VARCHAR(16),             -- 'nasm', 'gas', 'fasm', 'masm'
    synopsis TEXT,
    example TEXT
);
```

### Manual Registration Steps

1. **Log into Zetaris web UI**
2. **Create a database/schema** for barthelona facts (e.g., `barthelona_kb`)
3. **Create tables** using the schema above
4. **Insert data** — manually or via CSV import:
   - Linux syscalls: from `/usr/include/asm/unistd_64.h` or `syscall_64.tbl`
   - NASM instructions: from Appendix F of NASM manual
   - GAS directives: from `as.htm` pseudo-ops section
5. **Grant access** to your API key's organization

### Example: Populating Syscalls

```sql
-- In Zetaris SQL editor
INSERT INTO syscalls (name, nr, args, arch, abi) VALUES
('sys_read', 0, 'fd, buf, count', 'x86-64', 'sysv64'),
('sys_write', 1, 'fd, buf, count', 'x86-64', 'sysv64'),
('sys_open', 2, 'pathname, flags, mode', 'x86-64', 'sysv64'),
('sys_close', 3, 'fd', 'x86-64', 'sysv64'),
('sys_exit', 60, 'error_code', 'x86-64', 'sysv64');
-- ... continue for all syscalls
```

### Future: Automated Ingestion (Planned)

- `knowledge/sources.yaml` will define Zetaris as a source
- Ingestion pipeline: parse manuals → extract facts → upsert to Zetaris
- See [`docs/roadmap.md`](roadmap.md) Phase 3 for timeline

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
| Write operation attempted | Read-only: no `INSERT`/`UPDATE`/`DELETE`/`CREATE`/`DROP` |
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
rows = client.query("SELECT name, nr FROM syscalls WHERE nr < 10")
for row in rows:
    print(row)
```

---

## References

| Document                       | Link                                                                                                      |
| ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Quickstart (includes Zetaris)  | [`docs/quickstart.md`](quickstart.md)                                                                     |
| Current Status (detailed CLI)  | [`docs/current-status.md`](current-status.md#24-zetaris-status--zetaris-sql--structured-knowledge-store)  |
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
python -m barthelona chunked run "Write NASM sys_write wrapper" \
  --profile meterless \
  --facts-sql "SELECT nr, args FROM syscalls WHERE name = 'sys_write'" \
  --assemble --repair 2 \
  --out write_wrapper.asm
```

---

## Known Limitations (2026-10-24)

| Limitation                              | Status                                 |
| --------------------------------------- | -------------------------------------- |
| No automated fact ingestion pipeline    | Manual only (Phase 3)                  |
| Tested against fake HTTP transport only | Not yet validated against real Zetaris |
| Single-statement restriction            | By design (safety)                     |
| Read-only access                        | By design (safety)                     |
| No demo project using `--facts-sql`     | Planned                                |

---

_Last updated: 2026-10-24. For the latest, check `docs/current-status.md` and `docs/hackathon-demo.md`._
