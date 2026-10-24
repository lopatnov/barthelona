# What works today and how to run it

Status: 2026-10-24, Phase 0 plus the hackathon demo path. Check `docs/roadmap.md` for anything newer.

> **Integration guides:** [`docs/meterless-guide.md`](meterless-guide.md) | [`docs/zetaris-guide.md`](zetaris-guide.md) | [`docs/hackathon-demo-guide.md`](hackathon-demo-guide.md)

## The point

Barthelona exists to produce **correct** code, not code that looks right. A model proposes; tools decide
(AGENTS.md, invariant 1). `chunked run --assemble` is green only if NASM accepts the output. With
`--expect-stdout` and `--expect-exit` it also **runs the program in the Unicorn emulator** (never on your PC) and
requires the exact output and exit code, so a program that assembles but prints the wrong text is rejected and the
reason goes back to the model (D-056).

| Oracle                                                           | Status                                                                                                                          |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Syntax, assemble, link (V0-V2)                                   | works: `python -m barthelona verify <workspace>` and `chunked run --assemble` (assemble only)                                   |
| Sandboxed run with golden input/output (V5, V6)                  | works in `verify` for a workspace; not used by `chunked run`                                                                    |
| Run in the emulator, compare stdout and exit code                | works: `chunked run --expect-stdout ... --expect-exit ...` for single-file `_start` programs (Linux syscalls read, write, exit) |
| Static ABI lint (V3), dynamic ABI checks (V4)                    | library with 100% detection on the ABI corpus (`barthelona.emulator`); not yet a ladder level                                   |
| Create or edit a whole project from a request (Scrum engine, UI) | partly: a UI walking skeleton (#251) and a create flow for single-module programs through `worker` and `runs ...` (#253) are merged; multi-module sprints are not built |

## Install

Windows 11 with PowerShell is the tested host (Linux is supported by design, D-049).

1. **Python environment.** `.\scripts\create_env.ps1` creates the conda env `barthelona` (Python 3.13) with
   hash-locked dependencies. Then in your own terminal `. .\scripts\activate.ps1` (note the dot; it also loads `.env`).
   Check with `.\scripts\doctor.ps1`. Details and troubleshooting: `docs/runbook.md`.
2. **NASM** (needed by `--assemble`). Install it from https://www.nasm.us/. It is found through `--nasm`,
   `BARTHELONA_NASM`, `NASM_PATH` (a file or its folder), `PATH`, then the usual Windows folders.
3. **Meterless Nightshift** (the hackathon provider; it routes to local and cloud model lanes).
   - Install the Nightshift app from https://meterless.ai and start it. It serves an OpenAI-compatible endpoint at
     `http://127.0.0.1:8088/v1`.
   - In Nightshift: Setup, Providers: add your NVIDIA key (free endpoint). The key lives only there, never in `.env`.
   - NIGHT, LANES: add at least a Race lane with a Nemotron model (the dev PC's lane answered with
     `nvidia/nemotron-3-ultra-550b-a55b`; follow Nightshift's own model list, an earlier id here was not re-checked) and, to
     clear the red warning, a Judge or Verify lane on a different model. A model never grades its own answers.
   - Copy the runtime token from the Nightshift Console into `.env` as `METERLESS_RUNTIME_TOKEN`
     (`METERLESS_BASE_URL` only if the URL differs). `.env` is gitignored; never commit it.
   - Check: `python -m barthelona meterless status` prints `online` and the `meterless/*` routes, `unauthorized` for a
     wrong token, or `offline`.

   > **Full guide:** [`docs/meterless-guide.md`](meterless-guide.md) — installation, lane config, profiles, H-MEM, troubleshooting

4. **Optional.**
   - LM Studio or Ollama for a local fallback model (`docs/runbook.md` section 4). Profile `meterless` ends in the
     local model, so with LM Studio running a failed cloud call can silently fall back; stop it to see real errors.
   - WSL2 + Docker, only for `verify` (V5/V6) and `probe` (`docs/runbook.md` section 2).
   - Qdrant (`docs/runbook.md` section 3) and Zetaris (`python -m barthelona zetaris status`; Docker with 8 GB RAM).

   > **Full guide:** [`docs/zetaris-guide.md`](zetaris-guide.md) — installation, API key, SQL queries, `--facts-sql` injection, fact registration

## Run the hello demo

`demos/hello/task.txt` holds the prompt (the only human-written input). From the repository root, in the activated
terminal, as one command (`--assemble` and `--repair 2` are options of the same line):

```powershell
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/hello/hello.asm
```

- `--assemble` runs NASM on the code (`nasm -f elf64`, never linked or run on the host); the run is green only if it
  assembles. `--repair 2` gives NASM's errors back to the model for up to two more attempts.
- `--expect-stdout` and `--expect-exit` run the assembled program in the emulator and require that output and exit code.
  A mismatch counts as a rejection, so `--repair` gives the reason (for example `stdout was 'Hello,'`) back to the model.
- `--memory var/hmem.sqlite` recalls what earlier runs learned (H-MEM) and stores what a successful run learned.
  Run the command twice: the second run should recall facts and need fewer chunks.
- `--plan-role planner` and `--review-role cheap` add a plan before and an advisory review after; the assembler stays
  the oracle.
- Output: `demos/hello/hello.asm` (committed only after an `assemble: pass` run), `hello.asm.raw.txt` (the model's raw
  text, gitignored). Statistics: `python -m barthelona chunked stats` (per run and per answering model).

Read the result by the `assemble:` line (`pass`, `fail`, `unavailable`); with the expectations, `pass` means it also ran correctly. The `stop_reason=green` line is the chunk
loop's own marker, not the assembler's verdict.

## Create your own assembly program

Today a program is one NASM file (x86-64 Linux, `nasm -f elf64`). You describe it in a text file, Barthelona writes it
in chunks, NASM decides whether it is valid. You write no assembly.

1. **Write the task as plain text**, the way you would brief a colleague. Copy `demos/hello/task.txt` as a start:

   ```powershell
   mkdir demos\myprog
   copy demos\hello\task.txt demos\myprog\task.txt
   ```

   Say what the program must do, the platform (Linux x86-64, raw syscalls, no libc), the exact output and the exit
   code. The more concrete the task, the fewer repair rounds it needs. Keep it a prompt a person could write.

2. **Run it** from the repository root, in the activated terminal, as one line. The output goes to your folder, not to
   the repository root:

   ```powershell
   python -m barthelona chunked run @demos/myprog/task.txt --profile meterless --assemble --repair 2 --expect-stdout "<the exact output>\n" --expect-exit 0 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/myprog/myprog.asm
   ```

   - `@file` reads the task from the file; plain text in quotes works too.
   - `--repair-role planner` lets a deeper model do the repair rounds; `--plan-role planner` plans first.
   - `--facts-sql "SELECT ..."` gives the first chunk rows from Zetaris (required for the hackathon demo).

3. **Read the result.** `assemble: pass` means NASM accepted `demos/myprog/myprog.asm`. On `assemble: fail` the file is
   not trustworthy: read the errors, then `demos/myprog/myprog.asm.raw.txt` (the model's unfiltered text), sharpen the
   task and run again. Runs that share the `--memory` file reuse what earlier passing runs learned.
4. **Look at the numbers:** `python -m barthelona chunked stats` shows per model the chunks, tokens and time.
5. **Try the program yourself, outside Barthelona.** It was only assembled, never run. On Linux or in WSL:

   ```bash
   nasm -f elf64 demos/myprog/myprog.asm -o /tmp/myprog.o && ld /tmp/myprog.o -o /tmp/myprog && /tmp/myprog; echo $?
   ```

   Run only code you have read. The product never runs generated code on the host (invariant 2); this check is yours.
   The sandboxed run (V5/V6) is the part still to be wired into `chunked run`.

Not possible yet: several modules, other dialects (GAS, FASM), editing an existing project, or a pass that proves
behavior. Those need the Scrum engine and the emulator (Phase 1 and 2).

## Run the Streamlit UI (Phase 1a+)

```powershell
.\scripts\run.ps1                 # Windows: launches worker + Streamlit on http://127.0.0.1:8501
# or
scripts/run.sh                    # Linux / WSL
```

The UI provides three pages (Phase 1a walking skeleton):

- **New Request** — create a run: choose dialect/preset, mode (create/edit), prompt, budget, model profile (local-only / hybrid / cloud)
- **Approvals** — review and resolve human gates (G1 spec, G2 contracts, G4 final)
- **Live Run** — real-time event log tail, sprint topology DOT graph, run controls (cancel, extend budget)

Options:

```powershell
.\scripts\run.ps1 --worker-only   # only the worker (no UI)
.\scripts\run.ps1 --ui-only       # only the UI (assumes worker is running)
.\scripts\run.ps1 --port 8501     # custom Streamlit port
```

## Other commands

The worker, `runs submit/status/decide/package`, `check`, the `-LoadEnv` switch and the optional reasoning log
(`--trace-reasoning`) are described, with every flag, in [create-flow.md](create-flow.md).

## Troubleshooting

| Symptom                                                    | Likely cause                                                                                                                 |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `meterless status` says `unauthorized`                     | wrong or missing `METERLESS_RUNTIME_TOKEN`; your shell must have loaded `.env`                                               |
| `assemble: unavailable`                                    | NASM not found: set `BARTHELONA_NASM` to `nasm.exe`                                                                          |
| A chunk fell through to `local_main`                       | the Meterless route failed (see the error printed with it); LM Studio answered instead. Stop LM Studio to see the real error |
| Lane shows a timeout or "provider refused the key"         | NVIDIA key rejected or unreachable; re-enter it in Nightshift                                                                |
| Empty or truncated answers from a Nemotron reasoning model | the output budget ran out while it was thinking; raise `--chunk-tokens`                                                      |
| Red "no lane has duty Judge or Verify" in Nightshift Lanes | add a second chat lane and set Verify on it, preferably another model family; the only race lane cannot judge itself         |
| `stop_reason=green` but `assemble: fail`                   | `green` is the chunk loop's own marker; the `assemble:` line is the verdict                                                  |

## Known limits

- Small tasks are a poor fit for chunking: the model restates the whole program in every chunk, which caused the
  duplicate-label and unclosed-fence failures fixed in #224 and #228. Longer tasks show the effect better.
- All Nightshift lanes seen so far serve NVIDIA Nemotron models; "more than one model family" still needs a lane from
  another provider.
- Zetaris access is tested against a fake server only; registering a table of assembler facts is manual.
- Behavior is judged only when you pass `--expect-stdout` or `--expect-exit`, and only for single-file `_start` programs that use read, write, exit and getpid; libc, threads, sockets and SIMD are not emulated.

Hackathon design notes, what is ported from the Meterless engines and what is not: `docs/hackathon-demo.md`.
