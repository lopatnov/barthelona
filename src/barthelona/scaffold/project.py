"""Render the files of a produced single-module project: source, golden tests, README and workflows.

Everything here is a template or a table of the run's own data: the README says what the program does (from
the approved spec), how to build, run and test it, and how it was made (the request, the models and their
token and time totals). No model writes or reviews these files, so the same run data gives the same bytes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import PurePosixPath

import orjson

from barthelona.domain import LLMCallRecord, ProjectSpec, Run, TestCase
from barthelona.scaffold.ci import UnsupportedCiTarget, build_commands, render_ci, render_golden_ci

GOLDEN_TESTS = "tests/golden.json"
REQUEST_COPY = "prompt/request.txt"


def _model_rows(calls: Sequence[LLMCallRecord]) -> list[str]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0, 0.0])
    for call in calls:
        # The ledger's model id is already "<provider>/<name>" for catalog models; do not double the prefix.
        name = call.model if call.model.startswith(f"{call.provider}/") else f"{call.provider}/{call.model}"
        row = totals[name]
        row[0] += 1
        row[1] += call.tokens_in
        row[2] += call.tokens_out
        row[3] += call.latency_ms / 1000
    return [
        f"| `{name}` | {int(r[0])} | {int(r[1])} | {int(r[2])} | {r[3]:.1f} |"
        for name, r in sorted(totals.items())
    ]


def _test_line(case: TestCase) -> str:
    wanted = []
    if case.expect.stdout is not None:
        wanted.append(f"stdout `{case.expect.stdout!r}`")
    if case.expect.stdout_contains:
        wanted.append("stdout containing " + ", ".join(f"`{text!r}`" for text in case.expect.stdout_contains))
    output = " and ".join(wanted) or "any stdout"
    return (
        f"- **{case.id}**: stdin `{case.inputs.get('stdin', '')!r}` gives {output} "
        f"and exit code {case.expect.exit_code or 0}"
    )


def _readme(
    run: Run, spec: ProjectSpec, cases: Sequence[TestCase], request: str, calls: Sequence[LLMCallRecord]
) -> str:
    module = spec.modules[0].path
    artifact = f"{spec.slug}-linux-x86_64"
    requirements = "\n".join(f"- **{r.id}**: {r.text}" for r in spec.requirements)
    tests = "\n".join(_test_line(c) for c in cases)
    build = "\n".join(build_commands(spec))
    models = "\n".join(_model_rows(calls))
    repeat = (
        f"python -m barthelona runs submit @{REQUEST_COPY} "
        f"--profile {run.profile.value} --preset {run.target.preset}"
    )
    quoted = "\n".join(f"> {line}" if line else ">" for line in request.strip().splitlines())
    return f"""# {spec.slug}

{spec.summary_en}

Linux x86-64, written in NASM, no libc. This repository was produced by
[Barthelona](https://github.com/lopatnov/barthelona): a person wrote only the request below; the
specification, the tests, the source and these files were generated, and NASM and the emulator accepted the
source.

## Requirements

{requirements}

## Build and run

```
{build}
./build/{artifact}
```

Linux x86-64 only; on Windows use WSL2. Tagged releases (`v*`) carry the binary and its SHA-256.

## Test

The golden tests in `{GOLDEN_TESTS}` run the program in Barthelona's Unicorn emulator, never on the host.
A test passes when the exit code matches and stdout either matches exactly or, where a test lists texts,
contains each of them:

{tests}

```
python -m barthelona check {module} --tests {GOLDEN_TESTS}
```

The CI workflow installs a pinned Barthelona commit and runs that command. The result is not ABI-checked or
fuzzed: only the assembler and the emulated golden tests decided.

## How it was made

Request (also in `{REQUEST_COPY}`):

{quoted}

- Run `{run.id}`, profile `{run.profile.value}`, preset `{run.target.preset}`, policy `{run.policy_version}`.
- Gates G1 (specification and tests) and G4 (source) were approved by a person.
- Repeat it: `{repeat}`.

| Model | Calls | Tokens in | Tokens out | Seconds |
| --- | ---: | ---: | ---: | ---: |
{models}
"""


def render_project(
    run: Run,
    spec: ProjectSpec,
    cases: Sequence[TestCase],
    source: str,
    request: str,
    calls: Sequence[LLMCallRecord],
    barthelona_ref: str,
) -> dict[str, str]:
    """Project-relative path -> file text. Refuses what the templates cannot build (more than one module)."""
    if len(spec.modules) != 1:
        raise UnsupportedCiTarget(f"only single-module projects can be packaged, got {len(spec.modules)}")
    module = spec.modules[0].path
    workflows = render_ci(spec, barthelona_ref)  # the ladder CI needs contracts, which this slice has none of
    workflows[".github/workflows/ci.yml"] = render_golden_ci(spec, barthelona_ref, module, GOLDEN_TESTS)
    # A run only reaches a green verdict after a person approved gate G1, which freezes these tests.
    tests = [case.model_copy(update={"approved": True}).model_dump(mode="json") for case in cases]
    return {
        str(PurePosixPath(module)): source.rstrip("\n") + "\n",
        GOLDEN_TESTS: orjson.dumps(tests, option=orjson.OPT_INDENT_2).decode() + "\n",
        REQUEST_COPY: request.strip() + "\n",
        "README.md": _readme(run, spec, cases, request, calls),
        **workflows,
    }
