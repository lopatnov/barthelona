# demos/fizzbuzz: a task that needs several chunks

`task.txt` is the only human input: a prompt a person could write. The assembly is written by Barthelona into
`var/proof/` (gitignored) and is committed here only after a run that says `assemble: pass` with the emulator check.
Nothing in this folder is hand-written code.

Why this task: the hello program fits in one chunk, so a second run cannot need fewer chunks. FizzBuzz with its own
number-to-text routine is long enough that a small chunk size splits it. The expected output (FizzBuzz for 1 to 15) is
fixed by the task text, so the emulator check decides correctness, not the model.

Run from the repository root in PowerShell, one command, flags included. `--chunk-tokens 2000` keeps chunks small:

```powershell
.\scripts\dev.ps1 python -m barthelona chunked run @demos/fizzbuzz/task.txt --profile local-coder --plan-role planner --review-role cheap --repair-role planner --chunk-tokens 2000 --carryover-tokens 128 --max-chunks 8 --assemble --repair 2 --expect-stdout "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz\n" --expect-exit 0 --memory var/proof/fb-hmem.sqlite --stats var/proof/fb-runs.sqlite --out var/proof/fizzbuzz.asm
```

The `local-coder` profile uses three local model families through LM Studio: a Qwen coder writes the chunks, Codestral
plans and repairs, and Liquid reviews (advisory). Load or allow LM Studio to load `qwen2.5-coder-7b-instruct` and
`codestral-22b-v0.1`. `chunked stats` then shows the per-model table.

Run the same command twice and compare `chunks=` in the two summaries, then `python -m barthelona chunked stats --db
var/proof/fb-runs.sqlite`. The second run counts only if it also says `assemble: pass` and needs fewer chunks than the
first. If both runs finish in one chunk, the task is still too short for the model; say so instead of claiming a result.
