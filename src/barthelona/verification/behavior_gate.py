"""Decide a ``chunked run`` result by what the program does, not only by whether it assembles.

The assembled object is relocated and run in the Unicorn emulator (never on the host), and its stdout and exit
code are compared with the expectation. A mismatch comes back as a ``fail`` verdict with a plain-language
reason, so the repair loop can give it to the model exactly like an assembler error.
"""

from __future__ import annotations

from dataclasses import dataclass

from barthelona.emulator.machine import run_program
from barthelona.emulator.object_image import ImageError, load_object
from barthelona.verification.asm_gate import AssembleResult, assemble_object

_SHOWN = 200


@dataclass(frozen=True)
class Expectation:
    """What a correct program does; ``stdout`` None means the output is not checked exactly.

    ``contains`` are texts the output must hold, for programs whose other output is free.
    """

    stdout: bytes | None = None
    exit_code: int = 0
    stdin: bytes = b""
    contains: tuple[bytes, ...] = ()


def _shown(data: bytes) -> str:
    text = data[:_SHOWN].decode("utf-8", "backslashreplace")
    return repr(text) + ("..." if len(data) > _SHOWN else "")


def check_behavior(source: str, expect: Expectation, nasm: str | None = None) -> AssembleResult:
    """``pass`` when *source* assembles and, run in the emulator, prints and exits as expected."""
    gate, blob = assemble_object(source, nasm)
    if gate.status != "pass":
        return gate
    try:
        image = load_object(blob)
    except ImageError as exc:
        return AssembleResult("fail", (f"the object cannot be loaded for the run: {exc}",))
    if "_start" not in image.symbols:
        return AssembleResult("fail", ("the program has no global _start label to run",))
    run = run_program(image, image.symbols["_start"], expect.stdin)
    if run.status != "exit":
        reason = run.detail or {"timeout": "it ran too long", "limit": "it ran too many instructions"}.get(
            run.status, "it never called exit"
        )
        return AssembleResult("fail", (f"the program did not exit ({run.status}): {reason}",))
    problems = []
    if expect.stdout is not None and run.stdout != expect.stdout:
        problems.append(f"stdout was {_shown(run.stdout)}, expected {_shown(expect.stdout)}")
    problems += [
        f"stdout does not contain {_shown(text)}; it was {_shown(run.stdout)}"
        for text in expect.contains
        if text not in run.stdout
    ]
    if run.exit_code != expect.exit_code:
        problems.append(f"exit code was {run.exit_code}, expected {expect.exit_code}")
    return AssembleResult("fail", tuple(problems)) if problems else AssembleResult("pass")
