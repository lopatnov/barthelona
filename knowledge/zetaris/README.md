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

## Register the tables (an administrator, once)

Mount or copy the two CSV files where Zetaris can read them (`<path>` below), then run, one statement per call:

```sql
CREATE LIGHTNING DATABASE barthelona_files DESCRIBE BY "Barthelona knowledge tables";
CREATE LIGHTNING FILESTORE TABLE linux_x64_syscalls FROM barthelona_files FORMAT CSV
  OPTIONS (path "<path>/linux_x64_syscalls.csv", header "true", delimiter ",");
CREATE LIGHTNING FILESTORE TABLE abi_facts FROM barthelona_files FORMAT CSV
  OPTIONS (path "<path>/abi_facts.csv", header "true", delimiter ",");
```

The exact statement forms come from the Zetaris getting-started (`docs/guides/first-dataset.md`); check them
against your instance. Then:

```sql
SELECT name, arg1, arg2, arg3 FROM barthelona_files.linux_x64_syscalls WHERE name IN ('write', 'exit_group');
```
