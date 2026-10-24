# What works today and how to run it

Status: 2026-10-24, Phase 0 plus the hackathon demo path. Check `docs/roadmap.md` for anything newer.

## The point

Barthelona exists to produce **correct** code, not code that looks right. A model proposes; tools decide
(AGENTS.md, invariant 1). Today that decision is made by the assembler: a `chunked run --assemble` is green only if
NASM accepts the output. It is **not yet** made by running the program: nothing in the demo path checks that the
program prints the right text or exits with code 0. The pieces for that exist (V5/V6 run in a sandbox container and
compare output) but are not wired into `chunked run` (issue #206).

| Oracle | Status |
| --- | --- |
| Syntax, assemble, link (V0-V2) | works: `python -m barthelona verify <workspace>` and `chunked run --assemble` (assemble only) |
| Sandboxed run with golden input/output (V5, V6) | works in `verify` for a workspace; not used by `chunked run` |
| Static ABI lint (V3), Unicorn emulator (V4) | not built (Phase 2) |
| Create or edit a whole project from a request (Scrum engine, UI) | not built (Phase 1) |

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
   - NIGHT, LANES: add at least a Race lane (for example `nemotron-3.5-lightning-30b-a3b`) and, to clear the red
     warning, a Judge or Verify lane on a different model. A model never grades its own answers.
   - Copy the runtime token from the Nightshift Console into `.env` as `METERLESS_RUNTIME_TOKEN`
     (`METERLESS_BASE_URL` only if the URL differs). `.env` is gitignored; never commit it.
   - Check: `python -m barthelona meterless status` prints `online` and the `meterless/*` routes, `unauthorized` for a
     wrong token, or `offline`.
4. **Optional.**
   - LM Studio or Ollama for a local fallback model (`docs/runbook.md` section 4). Profile `meterless` ends in the
     local model, so with LM Studio running a failed cloud call can silently fall back; stop it to see real errors.
   - WSL2 + Docker, only for `verify` (V5/V6) and `probe` (`docs/runbook.md` section 2).
   - Qdrant (`docs/runbook.md` section 3) and Zetaris (`python -m barthelona zetaris status`; Docker with 8 GB RAM).

## Run the hello demo

`demos/hello/task.txt` holds the prompt (the only human-written input). From the repository root, in the activated
terminal, as one command (`--assemble` and `--repair 2` are options of the same line):

```powershell
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/hello/hello.asm
```

- `--assemble` runs NASM on the code (`nasm -f elf64`, never linked or run on the host); the run is green only if it
  assembles. `--repair 2` gives NASM's errors back to the model for up to two more attempts.
- `--memory var/hmem.sqlite` recalls what earlier runs learned (H-MEM) and stores what a successful run learned.
  Run the command twice: the second run should recall facts and need fewer chunks.
- `--plan-role planner` and `--review-role cheap` add a plan before and an advisory review after; the assembler stays
  the oracle.
- Output: `demos/hello/hello.asm` (committed only after an `assemble: pass` run), `hello.asm.raw.txt` (the model's raw
  text, gitignored). Statistics: `python -m barthelona chunked stats` (per run and per answering model).

Read the result by the `assemble:` line (`pass`, `fail`, `unavailable`). The `stop_reason=green` line is the chunk
loop's own marker, not the assembler's verdict.

## Other commands

| Command | What it does |
| --- | --- |
| `python -m barthelona version`, `schema [Document]` | version, domain JSON schemas |
| `python -m barthelona probe` | probe the `bart-tc` container, write `config/toolchains.lock.json` (needs WSL + Docker) |
| `python -m barthelona verify <workspace> --level V6` | run the ladder on a NASM or GAS workspace (needs WSL + Docker for V5/V6) |
| `python -m barthelona training status` | opt-in training-data setting and counts |
| `python -m barthelona bench ...` | benchmark models on the dev tasks |
| `python -m barthelona meterless status` | Nightshift online/unauthorized/offline and routes |
| `python -m barthelona zetaris status`, `zetaris sql "..."` | optional Zetaris facts store |

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `meterless status` says `unauthorized` | wrong or missing `METERLESS_RUNTIME_TOKEN`; your shell must have loaded `.env` |
| `assemble: unavailable` | NASM not found: set `BARTHELONA_NASM` to `nasm.exe` |
| A chunk fell through to `local_main` | the Meterless route failed (see the error printed with it); LM Studio answered instead |
| Lane shows a timeout or "provider refused the key" | NVIDIA key rejected or unreachable; re-enter it in Nightshift |
| Empty or truncated answers from a Nemotron reasoning model | the output budget ran out while it was thinking; raise `--chunk-tokens` |

Hackathon design notes, what is ported from the Meterless engines and what is not: `docs/hackathon-demo.md`.
