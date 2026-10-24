# demos/hello: the memory proof for the hackathon

Generated files from `chunked run` go here, never into the repository root. `task.txt` is the only human input: a
prompt a person could write. `hello.asm` is written by Barthelona and is committed only after a run in which NASM
accepted it and the emulator run printed the expected text and exited with 0 (`assemble: pass`). Run databases live in `var/` (gitignored); `*.raw.txt` files are gitignored.

Run from the repository root in the activated terminal (PowerShell, one command, flags included):

```powershell
python -m barthelona chunked run @demos/hello/task.txt --profile meterless --assemble --repair 2 --expect-stdout "Hello, Barthelona!\n" --expect-exit 0 --memory var/hmem.sqlite --stats var/runs.sqlite --out demos/hello/hello.asm
```

Run the same command twice, then show the statistics:

```powershell
python -m barthelona chunked stats
```

The second run counts only if it also says `assemble: pass` and uses fewer chunks than the first. NASM is found by
itself (see `docs/hackathon-demo.md`); set `NASM_PATH` to its folder if it is not.
