# Getting started: what works today, what to install, how to run it

Last updated 2026-10-24. This page is the honest list of what Barthelona can do **now**. The full design (Meta-Agentic
Scrum, UI, multi-file projects) is in `docs/architecture.md` and is not built yet; `docs/roadmap.md` is the source of
truth for phases.

## What "correct code" means today

Barthelona's rule is that **oracles decide and models propose** (`AGENTS.md`, invariant 1). Today the oracle for a
generated program is one real tool:

- `nasm -f elf64` must accept the source. The source is only assembled, never linked or run.
- Memory (H-MEM) is written only from a run that NASM accepted, so a rejected program teaches nothing.

What this does **not** prove yet: that the program behaves correctly (prints the right text, exits with code 0). That
needs the Unicorn emulator or the sandbox, which exist as verification levels (`verify`, V0-V2) but are not wired into
`chunked run`. A program that assembles is syntactically valid, not proven right.

## What works today

| Capability | Command | Needs |
| --- | --- | --- |
| Generate NASM code through the Meterless Nightshift provider, in bounded chunks with flat context | `python -m barthelona chunked run @task.txt --profile meterless --out out.asm` | conda env, Nightshift |
| Check the result with NASM and retry with NASM's errors (`--assemble --repair N`) | same, plus `--assemble --repair 2` | NASM |
| Run repair attempts on a deeper model | `--repair-role planner` | Nightshift |
| Remember what a passing run learned and recall it next time (H-MEM) | `--memory var/hmem.sqlite` | none |
| Per-model statistics (chunks, tokens, time, which model answered) | `--stats var/runs.sqlite`, then `python -m barthelona chunked stats` | none |
| Put rows from Zetaris in front of the first chunk as untrusted facts | `--facts-sql "SELECT ..."` | Zetaris, API key |
| Check the Nightshift connection | `python -m barthelona meterless status` | Nightshift |
| Check Zetaris | `python -m barthelona zetaris status`, `zetaris sql "SELECT ..."` | Zetaris |
| Run the verification ladder V0-V2 on a folder of assembly sources | `python -m barthelona verify <folder>` | Docker (WSL on Windows) |
| Version, domain schemas, training-data setting | `python -m barthelona version`, `schema`, `training status` | none |

Not built: creating or editing multi-file projects, the Streamlit UI, the Scrum loop, emulator checks inside
`chunked run`, GAS in `chunked run`. Do not expect them.

## What to install

1. **Python environment** (Windows): `.\scripts\create_env.ps1`, then in your terminal `. .\scripts\activate.ps1` (note
   the leading dot). Linux or Git Bash: `scripts/create_env.sh`, `source scripts/activate.sh`. Details and
   troubleshooting: `docs/runbook.md`.
2. **NASM**, the oracle. Windows: install it from nasm.us. It is found automatically if it is on PATH or in
   `%LOCALAPPDATA%\bin\NASM`, `%LOCALAPPDATA%\Programs\NASM`, `%ProgramFiles%\NASM`. Otherwise set `NASM_PATH` to its
   folder (or file) in `.env`, or pass `--nasm <path>`. Linux: `apt install nasm`. Without NASM, `--assemble` reports
   `unavailable`, never a pass.
3. **Meterless Nightshift** (the model provider), from meterless.ai (installed edition, not the browser demo):
   1. Install and start it, leave it running.
   2. In Nightshift: Setup, Providers, add **NVIDIA** with your key from build.nvidia.com. The NVIDIA key lives only
      in Nightshift, never in `.env`.
   3. NIGHT, LANES: add a lane in the **Race** row with a Nemotron model (for example
      `nvidia/nemotron-3.5-lightning-30b-a3b`) and start it. A second lane from another model family gives the
      per-model comparison; `meterless/auto` routes between lanes.
   4. Console (top right): copy the Nightshift URL and API key into `.env` as `METERLESS_BASE_URL` (only if it is not
      `http://127.0.0.1:8088/v1`) and `METERLESS_RUNTIME_TOKEN`.
   5. Check: `python -m barthelona meterless status` prints `online` and the `meterless/*` models.
4. **Zetaris** (optional): follow the hackathon guide (Docker, 8 GB memory, 15 GB disk), create the API key yourself
   in the Zetaris web interface and set `ZETARIS_API_KEY` (plus `ZETARIS_REST_URL`, `ZETARIS_ORG_ID` if not the
   defaults) in `.env`. Check: `python -m barthelona zetaris status`.
5. **LM Studio** (optional, local fallback, `http://127.0.0.1:1234/v1`) and **Docker/WSL** (only for `verify`):
   `docs/runbook.md` sections 2 to 4.

`.env` is read by `activate.ps1` only in your own terminal. Secrets never go into git.

## The proof run: the memory demo

`demos/hello/` holds the task (`task.txt`) and the one command. Run it twice from the repository root, then show the
statistics:

```powershell
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/hello/hello.asm
python -m barthelona chunked stats
```

Read the output like this:

- `assemble: pass` means NASM accepted the program; `assemble: fail (...)` shows NASM's errors and exits non-zero.
- `memory: recalled=N written=M` shows what the run read and wrote. `written=0 (assemble oracle: fail)` is correct for
  a rejected program.
- The second run counts as better only if it also passes and its summary shows fewer `chunks=` than the first.
- `chunked stats` lists, per model that answered, the chunks, tokens and average time.

`*.raw.txt` next to `--out` is the model's unfiltered text; use it to see why a run failed.

## Create your own assembly program

Today a program is one NASM file (x86-64 Linux, `nasm -f elf64`). You describe it in a text file, Barthelona writes it
in chunks, NASM decides whether it is valid. You write no assembly.

1. **Write the task as plain text**, the way you would brief a colleague. Copy `demos/hello/task.txt` as a start:

   ```powershell
   mkdir demos\myprog
   copy demos\hello\task.txt demos\myprog\task.txt
   ```

   Say what the program must do, the platform (Linux x86-64, raw syscalls, no libc), the exact output and the exit code.
   The more concrete the task, the fewer repair rounds it needs. Keep it a prompt a person could write.
2. **Run it** from the repository root, in the activated terminal, as one line. The output goes to your folder, not to
   the repository root:

   ```powershell
   python -m barthelona chunked run @demos/myprog/task.txt --profile meterless --assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/myprog/myprog.asm
   ```

   - `@file` reads the task from the file; plain text in quotes works too.
   - Add `--repair-role planner` to let a deeper model do the repair rounds, and `--plan-role planner` to plan first.
   - Add `--facts-sql "SELECT ..."` to give the first chunk rows from Zetaris (optional).
3. **Read the result.** `assemble: pass` means NASM accepted `demos/myprog/myprog.asm`. On `assemble: fail` the file is
   not trustworthy: read the errors, then `demos/myprog/myprog.asm.raw.txt` (the model's unfiltered text), sharpen the
   task and run again. Repeating a run with the same `--memory` file reuses what earlier passing runs learned.
4. **Look at the numbers:** `python -m barthelona chunked stats` shows per model the chunks, tokens and time.
5. **Try the program yourself, outside Barthelona.** It was only assembled, never run. On Linux or in WSL:

   ```bash
   nasm -f elf64 demos/myprog/myprog.asm -o /tmp/myprog.o && ld /tmp/myprog.o -o /tmp/myprog && /tmp/myprog; echo $?
   ```

   Run only code you have read. The product itself never runs generated code on the host (invariant 2); this check is
   yours, and the sandboxed run (V5/V6) is the part that is still to be wired in.

Not possible yet: several modules, other dialects (GAS, FASM), editing an existing project, or a pass that proves
behavior. Those need the Scrum engine and the emulator (Phase 1 and 2).

## Known limits

- Small tasks are a poor fit for chunking: the model restates the whole program in every chunk, which led to the
  duplicate and unclosed-fence failures fixed in #224 and #228. Longer tasks show the effect better.
- All Nightshift lanes seen so far serve NVIDIA Nemotron models; "more than one model family" still needs a lane from
  another provider.
- Zetaris access is tested against a fake server only; registering a table of assembler facts is manual.
- Nothing here has been judged on behavior, only on whether NASM accepts it.
