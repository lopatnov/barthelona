"""The optional reasoning log and the think-text extraction behind it."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.llm import ChatMessage, CompletionRequest, Gateway, RawReply
from barthelona.llm.catalog import Catalog, ChainEntry, ModelConfig, ProviderConfig
from barthelona.llm.thinking import think_text
from barthelona.llm.trace import ReasoningLog


@pytest.mark.parametrize(
    ("raw", "thought"),
    [
        ("<think>a</think>b", "a"),
        ("<think>a</think>b<think>c</think>d", "a\n\nc"),
        ("reasoning only</think>\nanswer", "reasoning only"),  # a template that opened the thought itself
        ("x<think>cut off", "cut off"),
        ("plain answer", ""),
    ],
)
def test_think_text_is_what_strip_think_removes(raw: str, thought: str) -> None:
    assert think_text(raw) == thought


class _Backend:
    def __init__(self, reply: RawReply) -> None:
        self._reply = reply

    def unsupported(self, target: object) -> str | None:
        return None

    async def complete(self, target: object, request: CompletionRequest) -> RawReply:  # NOSONAR S7503
        return self._reply


def _gateway(reply: RawReply, trace: ReasoningLog | None) -> Gateway:
    catalog = Catalog(
        providers={
            "lmstudio": ProviderConfig(kind="openai_chat", local=True, base_url="http://127.0.0.1:1/v1")
        },
        models={
            "local_main": ModelConfig(
                provider="lmstudio", model="m", price_class="local", context=1000, strip_think=True
            )
        },
        profiles={"p": {"worker": [ChainEntry(model="local_main")]}},
        default_profile="p",
    )
    return Gateway(catalog, {"openai_chat": _Backend(reply)}, env={}, trace=trace)  # type: ignore[arg-type]


def _request() -> CompletionRequest:
    return CompletionRequest(messages=(ChatMessage(role="user", content="hi"),))


def _reply(text: str, reasoning: str = "") -> RawReply:
    return RawReply(
        text=text, tokens_in=10, tokens_out=4, stop_reason="stop", latency_ms=2000, reasoning=reasoning
    )


async def test_the_log_gets_one_entry_per_request_with_reasoning_and_answer(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "reasoning.md"
    gateway = _gateway(_reply("<think>count the y answers</think>Score: 2"), ReasoningLog(log))
    await gateway.complete("worker", _request())
    await gateway.complete("worker", _request())
    text = log.read_text(encoding="utf-8")
    assert text.count("## worker via local_main (10 in, 4 out, 2.0s, stop=stop)") == 2
    assert "### reasoning\n\ncount the y answers\n\n### answer\n\nScore: 2" in text


async def test_a_separate_reasoning_field_wins_over_think_blocks(tmp_path: Path) -> None:
    log = tmp_path / "r.md"
    await _gateway(_reply("answer", reasoning="from the field"), ReasoningLog(log)).complete(
        "worker", _request()
    )
    assert "from the field" in log.read_text(encoding="utf-8")


async def test_a_reply_without_reasoning_says_so(tmp_path: Path) -> None:
    log = tmp_path / "r.md"
    await _gateway(_reply("plain"), ReasoningLog(log)).complete("worker", _request())
    assert "(the model sent no reasoning)" in log.read_text(encoding="utf-8")


async def test_a_log_that_cannot_be_written_does_not_lose_the_answer(tmp_path: Path) -> None:
    blocked = tmp_path / "is-a-file"
    blocked.write_text("x", encoding="utf-8")
    gateway = _gateway(_reply("the answer"), ReasoningLog(blocked / "log.md"))  # a file cannot be a folder
    done = await gateway.complete("worker", _request())
    assert done.text == "the answer"
    assert done.fallbacks[-1].startswith("reasoning log not written:")


async def test_a_dash_prints_to_stderr_and_no_log_is_the_default(capsys: pytest.CaptureFixture[str]) -> None:
    await _gateway(_reply("hi", reasoning="thought"), ReasoningLog("-")).complete("worker", _request())
    assert "thought" in capsys.readouterr().err
    await _gateway(_reply("hi", reasoning="secret thought"), None).complete("worker", _request())
    assert "secret thought" not in capsys.readouterr().err


async def test_an_echoing_log_writes_the_file_and_prints_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "r.md"
    await _gateway(_reply("hi", reasoning="visible thought"), ReasoningLog(log, echo=True)).complete(
        "worker", _request()
    )
    assert "visible thought" in log.read_text(encoding="utf-8")
    assert capsys.readouterr().err.count("visible thought") == 1
    await _gateway(_reply("hi", reasoning="dash thought"), ReasoningLog("-", echo=True)).complete(
        "worker", _request()
    )
    assert capsys.readouterr().err.count("dash thought") == 1  # '-' plus echo does not print twice
