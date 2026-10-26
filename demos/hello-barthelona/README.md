# hello-barthelona

Outputs the greeting 'Hello Barthelona' to standard output using Linux x86-64 syscalls.

Linux x86-64, written in NASM, no libc. This repository was produced by
[Barthelona](https://github.com/lopatnov/barthelona): a person wrote only the request below; the
specification, the tests, the source and these files were generated, and NASM and the emulator accepted the
source.

## Requirements

- **R1**: Writes exactly 'Hello Barthelona\n' to stdout.
- **R2**: Exits with status code 0 on success.

## Build and run

```
nasm -f elf64 -o build/hello.o src/hello.asm
ld -z noexecstack -e _start -o build/hello-barthelona-linux-x86_64 build/hello.o
./build/hello-barthelona-linux-x86_64
```

Linux x86-64 only; on Windows use WSL2. Tagged releases (`v*`) carry the binary and its SHA-256.

## Test

The golden tests in `tests/golden.json` run the program in Barthelona's Unicorn emulator, never on the host.
A test passes when the exit code matches and stdout either matches exactly or, where a test lists texts,
contains each of them:

- **T1**: stdin `''` gives stdout `'Hello Barthelona\n'` and exit code 0

```
python -m barthelona check src/hello.asm --tests tests/golden.json
```

The CI workflow installs a pinned Barthelona commit and runs that command. The result is not ABI-checked or
fuzzed: only the assembler and the emulated golden tests decided.

## How it was made

Request (also in `prompt/request.txt`):

> Make console application that outputs Hello Barthelona

- Run `run_b4e6dbdea5fa`, profile `meterless`, preset `linux-x64-nasm-static`, policy `v1`.
- Gates G1 (specification and tests) and G4 (source) were approved automatically: the run was started with auto-approve, so no person read them.
- Repeat it: `python -m barthelona runs submit @prompt/request.txt --profile meterless --preset linux-x64-nasm-static`.

| Model | Calls | Tokens in | Tokens out | Seconds |
| --- | ---: | ---: | ---: | ---: |
| `meterless/auto` | 7 | 43387 | 6212 | 137.8 |
| `meterless/deep` | 1 | 6468 | 827 | 14.1 |
