"""The Markovian chunk loop against a scripted FakeGateway: carryover, stop reasons, flat context."""

from __future__ import annotations

import pytest

from barthelona.domain.enums import StopReason
from barthelona.llm import FakeGateway, GatewayError, MarkovianConfig, run_markovian
from barthelona.llm.markovian import CHECKPOINT, COMPLETE, extract_code

_SMALL = MarkovianConfig(chunk_tokens=2400, carryover_tokens=128, max_chunks=4)


def _user_text(gateway: FakeGateway, call: int) -> str:
    return gateway.calls[call][1].messages[1].content


async def test_chunks_run_until_the_model_completes() -> None:
    gateway = FakeGateway(
        [f"part one\n{CHECKPOINT}\nCOMPLETED: one. REMAINING: two. DECISIONS: none", f"part two\n{COMPLETE}"],
    )
    result = await run_markovian(gateway, "worker", "write two parts", _SMALL)
    assert result.stop_reason is StopReason.GREEN
    assert result.text == "part one\npart two"
    assert [chunk.marker for chunk in result.chunks] == ["checkpoint", "complete"]
    assert [chunk.carryover for chunk in result.chunks] == ["state_block", "none"]


async def test_second_chunk_sees_only_the_state_block_not_the_previous_output() -> None:
    gateway = FakeGateway(
        [f"long body\n{CHECKPOINT}\nREMAINING: two, with all the names it needs", f"x\n{COMPLETE}"]
    )
    await run_markovian(gateway, "worker", "task", _SMALL)
    assert "REMAINING: two, with all the names it needs" in _user_text(gateway, 1)
    assert "long body" not in _user_text(gateway, 1)
    assert "first step" in _user_text(gateway, 0)


async def test_missing_marker_carries_the_tail_of_the_chunk() -> None:
    gateway = FakeGateway(["a" * 1000 + "TAIL", f"done\n{COMPLETE}"])
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.chunks[0].carryover == "tail"
    assert "TAIL" in _user_text(gateway, 1)
    assert len(_user_text(gateway, 1)) < 1200


async def test_the_loop_is_bounded_by_max_chunks() -> None:
    gateway = FakeGateway([f"p\n{CHECKPOINT}\nCOMPLETED: a. REMAINING: b. DECISIONS: c."] * 10)
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.stop_reason is StopReason.MAX_ATTEMPTS
    assert len(result.chunks) == _SMALL.max_chunks
    assert len(gateway.calls) == _SMALL.max_chunks


async def test_a_gateway_failure_keeps_the_finished_chunks_and_says_why() -> None:
    gateway = FakeGateway(
        [f"p1\n{CHECKPOINT}\nCOMPLETED: a. REMAINING: b. DECISIONS: c.", GatewayError("down")]
    )
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.stop_reason is StopReason.NO_MODEL_AVAILABLE
    assert result.text == "p1"
    assert len(result.chunks) == 1


async def test_each_call_asks_for_a_bounded_answer() -> None:
    gateway = FakeGateway([f"x\n{COMPLETE}"])
    await run_markovian(gateway, "worker", "task", _SMALL)
    assert gateway.calls[0][1].max_tokens == 2400 - 128 - 400


@pytest.mark.parametrize(
    ("chunk", "carry", "chunks"), [(1000, 800, 4), (8000, 64, 4), (8000, 800, 0), (8000, 800, 33)]
)
def test_config_rejects_values_outside_the_engine_ranges(chunk: int, carry: int, chunks: int) -> None:
    with pytest.raises(ValueError, match="must be"):
        MarkovianConfig(chunk_tokens=chunk, carryover_tokens=carry, max_chunks=chunks)


def test_extract_code_keeps_only_the_fenced_blocks() -> None:
    text = "Plan:\n1. write\n```asm\nsection .text\n```\nnote\n```nasm\n_start:\n    ret\n```\nbye"
    assert extract_code(text) == "section .text\n_start:\n    ret"
    assert extract_code("no code here") == ""


def test_extract_code_drops_a_block_that_repeats_the_program_without_its_comments() -> None:
    program = "section .text\nglobal _start\n_start:\n    mov rax, 60  ; exit\n    syscall"
    again = "section .text\nglobal _start\n_start:\n    mov rax, 60\n    syscall"
    text = f"```asm\n{program}\n```\nand once more\n```asm\n{again}\n```"
    assert extract_code(text) == program


def test_extract_code_keeps_a_second_block_that_adds_new_lines() -> None:
    first = "section .data\nmsg db 'a'\nlen equ 1"
    second = "section .text\nglobal _start\n_start:\n    syscall"
    assert extract_code(f"```asm\n{first}\n```\n```asm\n{second}\n```") == f"{first}\n{second}"


def test_extract_code_drops_shell_commands_and_output_blocks() -> None:
    text = (
        "```asm\n_start:\n```\n```bash\nnasm -f elf64 hello.asm\n```\n"
        "```\nuntagged source\n```\n```text\nHello\n```"
    )
    assert extract_code(text) == "_start:\nuntagged source"


def test_extract_code_drops_untagged_blocks_that_only_run_build_tools() -> None:
    text = (
        "```\nnasm -f elf64 -o hello.o hello.asm\n```\n"
        "```\n$ ld -o hello hello.o\n$ ./hello\n```\n"
        "```nasm\nsection .text\n```"
    )
    assert extract_code(text) == "section .text"


async def test_a_state_block_shorter_than_24_chars_falls_back_to_the_tail() -> None:
    gateway = FakeGateway([f"real work here\n{CHECKPOINT}\ntoo short", f"x\n{COMPLETE}"])
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.chunks[0].carryover == "tail"


async def test_cost_model_follows_the_spec_formulas() -> None:
    state = "COMPLETED: a. REMAINING: b. DECISIONS: c."
    gateway = FakeGateway(
        [f"w1 w2 w3\n{CHECKPOINT}\n{state}", f"w4 w5\n{CHECKPOINT}\n{state}", f"w6\n{COMPLETE}"]
    )
    result = await run_markovian(gateway, "worker", "task", MarkovianConfig(2400, 128, 8))
    sizes = [chunk.tokens for chunk in result.chunks]
    assert result.standard_cost == sizes[0] + (sizes[0] + sizes[1]) + sum(sizes)
    assert result.markovian_cost == 3 * 128 + sum(sizes)
    assert result.status == "completed"
    assert 0 <= result.efficiency_percent <= 100


async def test_the_completing_chunk_keeps_the_state_written_after_its_marker() -> None:
    state = "DECISIONS: exit through sys_exit. CONTEXT: the message ends with a newline."
    gateway = FakeGateway([f"```asm\n_start:\n```\n{COMPLETE}\n{state}"])
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.chunks[0].marker == "complete"
    assert result.chunks[0].state == state
    assert result.chunks[0].carryover == "none"
    assert result.text == "```asm\n_start:\n```"


async def test_a_single_chunk_run_reports_too_short_to_compare_not_zero_percent() -> None:
    result = await run_markovian(FakeGateway([f"x\n{COMPLETE}"]), "worker", "task", _SMALL)
    assert result.markovian_cost > result.standard_cost
    assert result.efficiency_label == "too short to compare"


async def test_a_run_that_saves_tokens_reports_the_percentage() -> None:
    body = "w " * 4000
    state = "COMPLETED: a. REMAINING: b. DECISIONS: c."
    gateway = FakeGateway([f"{body}\n{CHECKPOINT}\n{state}"] * 5 + [f"{body}\n{COMPLETE}"])
    result = await run_markovian(gateway, "worker", "task", MarkovianConfig(8000, 128, 8))
    assert result.efficiency_label == f"{result.efficiency_percent:.1f}%"
    assert result.efficiency_percent > 0


async def test_chunk_stats_keep_the_reasons_earlier_chain_entries_were_skipped() -> None:
    from barthelona.llm.types import Completion

    class _Fallback(FakeGateway):
        async def complete(self, role, request):  # type: ignore[no-untyped-def]
            done = await super().complete(role, request)
            return Completion(
                text=done.text,
                record=done.record,
                served_by="local_main",
                fallbacks=("meterless_auto: boom",),
            )

    result = await run_markovian(_Fallback([f"x\n{COMPLETE}"]), "worker", "task", _SMALL)
    assert result.chunks[0].fallbacks == ("meterless_auto: boom",)


_UNCLOSED_RAW = """```asm
section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg
section .text
    global _start
_start:
    mov rax, 1
    mov rsi, msg
```asm
section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg
section .text
    global _start
_start:
    mov rax, 1
    mov rsi, msg
    mov rdx, msg_len
    syscall
    mov rax, 60
    xor rdi, rdi
```asm
section .data
    msg db "Hello, Barthelona!", 10
    msg_len equ $ - msg
section .text
    global _start
_start:
    mov rax, 1
    mov rsi, msg
    mov rdx, msg_len
    syscall
    mov rax, 60
    xor rdi, rdi
    syscall
```
"""


def test_extract_code_survives_blocks_the_model_never_closed() -> None:
    code = extract_code(_UNCLOSED_RAW)
    assert "```" not in code
    assert code.count("_start:") == 1
    assert code.rstrip().endswith("syscall")


def test_a_block_left_open_at_the_end_of_the_text_is_kept() -> None:
    assert extract_code("```asm\nsection .text\n_start:\n    ret") == "section .text\n_start:\n    ret"


def test_a_stray_fence_before_a_tagged_block_does_not_hide_it() -> None:
    text = "```\n```asm\nsection .text\n_start:\n    ret\n```"
    assert extract_code(text) == "section .text\n_start:\n    ret"


_STATE = "COMPLETED: wrote the write syscall. REMAINING: exit. DECISIONS: none"


async def test_recall_gives_every_later_chunk_a_fresh_memory_block() -> None:
    seen: list[str] = []
    gateway = FakeGateway([f"a\n{CHECKPOINT}\n{_STATE}", f"b\n{COMPLETE}"])

    def recall(state: str) -> str:
        seen.append(state)
        return f"[MEMORY CONTEXT] for {len(seen)}"

    result = await run_markovian(gateway, "worker", "task", _SMALL, "[MEMORY CONTEXT] first", recall)
    assert len(result.chunks) == 2
    assert len(seen) == 1 and "write syscall" in seen[0]  # asked once, for chunk 2, with the carryover
    assert _user_text(gateway, 0).startswith("[MEMORY CONTEXT] first")
    assert _user_text(gateway, 1).startswith("[MEMORY CONTEXT] for 1")


async def test_without_recall_later_chunks_get_no_memory_block() -> None:
    gateway = FakeGateway([f"a\n{CHECKPOINT}\n{_STATE}", f"b\n{COMPLETE}"])
    await run_markovian(gateway, "worker", "task", _SMALL, "[MEMORY CONTEXT] first")
    assert "[MEMORY CONTEXT]" in _user_text(gateway, 0)
    assert "[MEMORY CONTEXT]" not in _user_text(gateway, 1)
