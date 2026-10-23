"""The Markovian chunk loop against a scripted FakeGateway: carryover, stop reasons, flat context."""

from __future__ import annotations

import pytest

from barthelona.domain.enums import StopReason
from barthelona.llm import FakeGateway, GatewayError, MarkovianConfig, run_markovian
from barthelona.llm.markovian import CHECKPOINT, COMPLETE

_SMALL = MarkovianConfig(chunk_tokens=2400, carryover_tokens=128, max_chunks=4)


def _user_text(gateway: FakeGateway, call: int) -> str:
    return gateway.calls[call][1].messages[1].content


async def test_chunks_run_until_the_model_completes() -> None:
    gateway = FakeGateway(
        [f"part one\n{CHECKPOINT}\ndone: one; next: two", f"part two\n{COMPLETE}"],
    )
    result = await run_markovian(gateway, "worker", "write two parts", _SMALL)
    assert result.stop_reason is StopReason.GREEN
    assert result.text == "part one\npart two"
    assert [chunk.marker for chunk in result.chunks] == ["checkpoint", "complete"]
    assert [chunk.carryover for chunk in result.chunks] == ["state_block", "none"]


async def test_second_chunk_sees_only_the_state_block_not_the_previous_output() -> None:
    gateway = FakeGateway([f"long body\n{CHECKPOINT}\nnext: two", f"x\n{COMPLETE}"])
    await run_markovian(gateway, "worker", "task", _SMALL)
    assert "next: two" in _user_text(gateway, 1)
    assert "long body" not in _user_text(gateway, 1)
    assert "first step" in _user_text(gateway, 0)


async def test_missing_marker_carries_the_tail_of_the_chunk() -> None:
    gateway = FakeGateway(["a" * 1000 + "TAIL", f"done\n{COMPLETE}"])
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.chunks[0].carryover == "tail"
    assert "TAIL" in _user_text(gateway, 1)
    assert len(_user_text(gateway, 1)) < 1200


async def test_the_loop_is_bounded_by_max_chunks() -> None:
    gateway = FakeGateway([f"p\n{CHECKPOINT}\ns"] * 10)
    result = await run_markovian(gateway, "worker", "task", _SMALL)
    assert result.stop_reason is StopReason.MAX_ATTEMPTS
    assert len(result.chunks) == _SMALL.max_chunks
    assert len(gateway.calls) == _SMALL.max_chunks


async def test_a_gateway_failure_keeps_the_finished_chunks_and_says_why() -> None:
    gateway = FakeGateway([f"p1\n{CHECKPOINT}\ns", GatewayError("down")])
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
