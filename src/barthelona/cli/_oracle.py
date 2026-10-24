"""The oracle loop of ``chunked run``: attempt, let the assembler (and the emulator) decide, repair."""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from barthelona.llm import MarkovianResult
from barthelona.llm.guard import wrap_untrusted
from barthelona.llm.markovian import source_blocks
from barthelona.verification.asm_gate import AssembleResult, assemble_best
from barthelona.verification.behavior_gate import Expectation, check_behavior

NO_ORACLE = ""  # the sentinel for "do not assemble"; a real binary name is never empty

Attempt = Callable[[str, int], tuple[MarkovianResult, str]]
_err = Console(stderr=True, soft_wrap=True, highlight=False)


def until_it_passes(
    attempt: Attempt, task: str, nasm: str | None, repair: int, expect: Expectation | None = None
) -> tuple[MarkovianResult, str, AssembleResult | None]:
    """The first attempt plus up to *repair* retries that get the oracle's errors; no gate when it is off."""
    result, text = attempt(task, 0)
    if nasm == NO_ORACLE:
        return result, text, None
    text, gate = _judge(result, text, nasm, expect)
    for number in range(1, repair + 1):
        if gate.status != "fail":
            break
        _err.print(
            f"oracle: rejected, repair attempt {number}/{repair}: {'; '.join(gate.errors)}", markup=False
        )
        result, text = attempt(_repair_task(task, text, gate, expect is not None), number)
        text, gate = _judge(result, text, nasm, expect)
    return result, text, gate


def _judge(
    result: MarkovianResult, text: str, nasm: str | None, expect: Expectation | None
) -> tuple[str, AssembleResult]:
    """Assemble the joined code, or one block of it when the blocks together do not (and say so)."""
    chosen, gate = assemble_best(text, source_blocks(result.text), nasm)
    if chosen != text:
        _err.print("assemble: the joined blocks were rejected; one block alone assembles and is used")
    if expect is not None and gate.status == "pass":
        gate = check_behavior(chosen, expect, nasm)
    return chosen, gate


def _repair_task(task: str, source: str, gate: AssembleResult, behavior: bool) -> str:
    errors = wrap_untrusted("\n".join(gate.errors), "oracle")
    what = "was rejected when it was assembled and run" if behavior else "did not assemble"
    return (
        f"{task}\n\nYour previous attempt {what}. The checker reported:\n{errors}\n\n"
        f"Previous source:\n```asm\n{source}\n```\n"
        "Write the complete corrected program exactly once, in a single fenced block."
    )
