# demos/hello

Scratch folder for the smallest Barthelona demo: one NASM x86-64 Linux file that prints a greeting and exits with code 0.
Everything Barthelona writes here (`hello.asm`, its `.raw.txt`, objects) is generated and git-ignored; only this README,
`task.txt` and the `.gitignore` are tracked. Nothing in this folder is hand-written code.

This is a placeholder until the engine can build a full demo repo (AGENTS.md, "Demos are Barthelona's output"). The
other demos under `demos/` are separate repositories.

## Inputs

- Prompt: `task.txt` in this folder, the only human-written input (`Write a NASM x86-64 Linux program that prints 'Hello, Barthelona' and exits with code 0. Use sys_write and sys_exit syscalls only.`)
- Profile `meterless` (Meterless Nightshift lanes, see `docs/hackathon-demo.md`); models are whatever the lanes hold.
- Oracle: NASM assembles the output (`nasm -f elf64`, never linked or run).

## Run

From the repository root, in the activated terminal. `--assemble` and `--repair 2` are flags of the same command:
put them on the same line after the task text, in any order.

```powershell
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --memory var/hmem.sqlite --stats var/runs.sqlite --plan-role planner --review-role cheap --out demos/hello/hello.asm
```

NASM is found through `--nasm`, the `BARTHELONA_NASM` variable, PATH or the usual install folders. `--code` is implied by
`--assemble`. Run it twice with the same `--memory` file to see the second run recall what the first one learned, then
`python -m barthelona chunked stats` for the per-run and per-model tables.
