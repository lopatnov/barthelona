import json

import httpx
import pytest

from barthelona.llm.hmem import HMem
from barthelona.llm.zetaris import ZetarisConfig
from barthelona.llm.zetaris_memory import fact_text, seed_hmem

CONFIG = ZetarisConfig("http://zetaris.test/api/v1.0", "1", "k")


@pytest.fixture
def zetaris(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        sql = json.loads(request.content)["sql"]
        if "linux_x64_syscalls" in sql:
            data = [[1, "write", "rdi=fd", "rsi=buf", "rdx=count", None, None, None, "returns bytes written"]]
        else:
            data = [["syscall_instruction", "number in rax, arguments in rdi rsi rdx r10 r8 r9"]]
        return httpx.Response(200, json={"data": data})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))


def test_fact_text_drops_empty_cells() -> None:
    assert fact_text("syscall", ("1", "write", "None", "")) == "syscall: 1 | write"


def test_seed_writes_sourced_facts_once_and_recall_finds_them(zetaris: None) -> None:
    store = HMem()
    assert seed_hmem(CONFIG, store) == 2
    assert seed_hmem(CONFIG, store) == 0  # a re-seed reinforces, it does not duplicate
    assert store.count() == 2
    recall = store.query("write a string to stdout with the write syscall", domain="assembly")
    assert recall.memories
    assert recall.memories[0].source == "zetaris:barthelona_files.linux_x64_syscalls"
    assert "rdi=fd" in recall.context
