# Zetaris knowledge tables

Facts for the agent's spec and coder steps, loaded into Zetaris and read with `SELECT` (Open Agent
Hackathon; `src/barthelona/llm/zetaris.py` is read-only by design).

| File | Table | Rows |
| --- | --- | --- |
| `linux_x64_syscalls.csv` | `barthelona.linux_x64_syscalls` | common Linux x86-64 syscalls with argument registers |
| `abi_facts.csv` | `barthelona.abi_facts` | syscall and System V AMD64 conventions, NASM build line |

**Provenance.** The numbers and conventions are the public Linux x86-64 syscall table (`syscall(2)`,
`arch/x86/entry/syscalls/syscall_64.tbl`) and the System V AMD64 psABI. They were written from memory of those
sources and still need a `docs-researcher` check against the kernel table and the psABI before anything depends
on them (AGENTS.md "Facts").

## Register the tables (once)

Verified on the hackathon Docker stack (2026-10-24). The api and driver containers share the volume
`zetaris_customer-data` at `/home/zetaris/customer-data`, so copy the files in with a relative path (an absolute
`C:\` path makes `docker cp` read `C` as a container name), from this folder:

```
docker exec <driver> mkdir -p /home/zetaris/customer-data/shared/barthelona
docker cp ./linux_x64_syscalls.csv <driver>:/home/zetaris/customer-data/shared/barthelona/linux_x64_syscalls.csv
docker cp ./abi_facts.csv <driver>:/home/zetaris/customer-data/shared/barthelona/abi_facts.csv
```

Then send each statement as its own `POST <rest url>/sql-editor/sqls/run` (the API key was accepted for CREATE).
A second run probably fails with "already exists"; check `SHOW LIGHTNING TABLES barthelona_files` first.

```sql
CREATE LIGHTNING DATABASE barthelona_files DESCRIBE BY "Barthelona knowledge tables";
CREATE LIGHTNING FILESTORE TABLE linux_x64_syscalls FROM barthelona_files FORMAT CSV
  OPTIONS (path "/home/zetaris/customer-data/shared/barthelona/linux_x64_syscalls.csv", header "true", delimiter ",");
CREATE LIGHTNING FILESTORE TABLE abi_facts FROM barthelona_files FORMAT CSV
  OPTIONS (path "/home/zetaris/customer-data/shared/barthelona/abi_facts.csv", header "true", delimiter ",");
```

With `ZETARIS_API_KEY` set the worker reads both tables into the spec and test-author prompts by default
(`engine/host.py` `DEFAULT_FACTS_SQL`); `--facts-sql` overrides it. A down Zetaris gives no facts, not a failed run.

Check it:

```sql
SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name IN ('write', 'exit_group');
```

## Publish run history and memory (SQLite stays the store)

`python -m barthelona zetaris publish <driver container>` exports `var/runs.sqlite` (`runs`, `run_chunks`) and
`var/hmem.sqlite` (`memories`, `memory_ledger`) to CSV, copies them into the shared volume and registers them once as
tables in `barthelona_runtime`. Repeat it after runs to refresh the files. Then, for example:

```sql
SELECT label, profile, chunks, recalled FROM barthelona_runtime.runs ORDER BY id DESC;
```
