"""H-MEM store, ranking and the Markovian hand-off: recall into chunk 0, write-back at the end."""

from __future__ import annotations

import pytest

from barthelona.domain.enums import StopReason
from barthelona.llm import FakeGateway, MarkovianConfig, run_markovian
from barthelona.llm.hmem import HMem, facts_from_state
from barthelona.llm.markovian import CHECKPOINT, COMPLETE

_SMALL = MarkovianConfig(chunk_tokens=2400, carryover_tokens=128, max_chunks=4)
_STATE = (
    "COMPLETED: data section. REMAINING: exit syscall. "
    "DECISIONS: use `sys_write` then `sys_exit` on x86-64 Linux. "
    "CONTEXT: label _start is the entry point of hello.asm"
)


def _store() -> HMem:
    clock = iter(range(1000, 10_000))
    return HMem(clock=lambda: float(next(clock)))


def test_facts_come_from_decisions_and_context_only() -> None:
    facts = facts_from_state(_STATE.replace(". ", "\n"))
    assert len(facts) == 2
    assert facts[0].startswith("use `sys_write`")
    assert not any("exit syscall" in fact for fact in facts)


def test_short_facts_are_not_trusted() -> None:
    assert facts_from_state("DECISIONS: ok") == []


def test_a_memory_without_a_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="source"):
        _store().ingest(["something long enough to be a fact"], source="", domain="assembly")


def test_recall_finds_what_was_written_and_orders_by_relevance() -> None:
    store = _store()
    store.ingest(
        ["use sys_write then sys_exit on x86-64 Linux", "the cat sat on the warm mat all day long"],
        source="markovian:run-1",
        domain="assembly",
    )
    recall = store.query("write a nasm program that calls sys_write and sys_exit", domain="assembly")
    assert recall.memories[0].content.startswith("use sys_write")
    assert "[MEMORY CONTEXT]" in recall.context
    assert "markovian:run-1" in recall.context


def test_nothing_recalled_gives_an_empty_context() -> None:
    assert _store().query("anything", domain="assembly").context == ""


def test_a_repeated_fact_is_reinforced_not_duplicated_and_the_ledger_records_it() -> None:
    store = _store()
    fact = "exit with code 0 through the sys_exit syscall"
    assert store.ingest([fact], source="a", domain="assembly") == 1
    assert store.ingest([fact], source="b", domain="assembly") == 0
    assert store.count() == 1
    assert store.ledger_size() == 2


def test_other_domains_rank_lower_than_the_queried_one() -> None:
    store = _store()
    store.ingest(["sys_write prints the text to stdout"], source="a", domain="web")
    store.ingest(["sys_write prints the text to stdout always"], source="b", domain="assembly")
    recall = store.query("sys_write prints text", domain="assembly", threshold=0.0)
    assert recall.memories[0].domain == "assembly"


async def test_a_run_that_completes_in_one_chunk_still_writes_its_decisions() -> None:
    state = "DECISIONS: use sys_write then sys_exit on Linux x86-64. CONTEXT: end the message with a newline."
    result = await run_markovian(FakeGateway([f"a\n{COMPLETE}\n{state}"]), "worker", "task", _SMALL)
    facts = [fact for chunk in result.chunks for fact in facts_from_state(chunk.state)]
    assert len(facts) == 2
    assert _store().ingest(facts, source="markovian:run-1", domain="assembly") == 2


async def test_second_run_gets_the_first_runs_decisions_in_chunk_zero_only() -> None:
    store = _store()
    first = FakeGateway([f"a\n{CHECKPOINT}\n{_STATE}", f"b\n{COMPLETE}"])
    task = "write a nasm hello program that calls sys_write and sys_exit"
    result = await run_markovian(first, "worker", task, _SMALL, store.query(task, domain="assembly").context)
    assert "[MEMORY CONTEXT]" not in first.calls[0][1].messages[1].content
    facts = [fact for chunk in result.chunks for fact in facts_from_state(chunk.state)]
    assert store.ingest(facts, source="markovian:run-1", domain="assembly") == 2

    second = FakeGateway([f"c\n{CHECKPOINT}\n{_STATE}", f"d\n{COMPLETE}"])
    await run_markovian(second, "worker", task, _SMALL, store.query(task, domain="assembly").context)
    assert "[MEMORY CONTEXT]" in second.calls[0][1].messages[1].content
    assert "sys_write" in second.calls[0][1].messages[1].content
    assert "[MEMORY CONTEXT]" not in second.calls[1][1].messages[1].content
    assert result.stop_reason is StopReason.GREEN
