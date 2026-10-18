"""Unit and property tests for the FILE envelope parser."""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from barthelona.prompting import EnvelopeError, FileBlock, parse_files, render_files


def test_parses_files_in_order_and_ignores_prose() -> None:
    reply = (
        "Here you go:\n=== FILE: src/a.asm ===\nmov rax, 1\nret\n=== END ===\n"
        "and also\n=== FILE: src/b.asm ===\nnop\n=== END ===\nbye"
    )
    assert parse_files(reply) == [
        FileBlock("src/a.asm", "mov rax, 1\nret\n"),
        FileBlock("src/b.asm", "nop\n"),
    ]


def test_crlf_replies_are_normalised() -> None:
    assert parse_files("=== FILE: a.s ===\r\nnop\r\n=== END ===\r\n") == [FileBlock("a.s", "nop\n")]


def test_blank_lines_and_indentation_inside_a_file_are_kept() -> None:
    (block,) = parse_files("=== FILE: a.s ===\n\n  mov rax, 1\n\n=== END ===")
    assert block.content == "\n  mov rax, 1\n\n"


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ("just prose", "no '=== FILE"),
        ("=== FILE: a.s ===\nnop\n", "missing '=== END ===' (reply cut off?)"),
        ("=== FILE: a.s ===\nnop\n=== FILE: b.s ===\nnop\n=== END ===", "'a.s': missing '=== END ==='"),
        ("=== FILE: /etc/passwd ===\nx\n=== END ===", "'/etc/passwd'"),
        ("=== FILE: ../x.s ===\nx\n=== END ===", "'../x.s'"),
        ("=== FILE: a\\b.s ===\nx\n=== END ===", "a\\\\b.s"),
        ("=== FILE: a.s ===\n\n=== END ===", "empty file"),
        ("=== FILE: a.s ===\n```asm\nnop\n```\n=== END ===", "markdown code fence"),
        ("=== FILE: a.s ===\nx\n=== END ===\n=== FILE: a.s ===\ny\n=== END ===", "appears twice"),
    ],
)
def test_rejects_with_a_message_that_names_the_problem(reply: str, message: str) -> None:
    with pytest.raises(EnvelopeError) as raised:
        parse_files(reply)
    assert message in str(raised.value)


def test_write_scope_fences_paths() -> None:
    reply = "=== FILE: src/a.s ===\nnop\n=== END ===\n=== FILE: tests/t.s ===\nnop\n=== END ==="
    with pytest.raises(EnvelopeError, match=r"'tests/t\.s' is outside the write scope"):
        parse_files(reply, write_scope=["src/*.s"])
    assert [f.path for f in parse_files(reply, write_scope=["src/*.s", "tests/*.s"])] == [
        "src/a.s",
        "tests/t.s",
    ]


def test_all_errors_are_reported_together_capped_at_ten() -> None:
    reply = "".join(f"=== FILE: ../{i}.s ===\nx\n=== END ===\n" for i in range(15))
    with pytest.raises(EnvelopeError) as raised:
        parse_files(reply)
    assert len(raised.value.errors) == 10


_PATHS = st.from_regex(r"[a-z][a-z0-9_]{0,8}(/[a-z][a-z0-9_]{0,8}){0,2}\.(asm|s)", fullmatch=True)
_LINES = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="`"), max_size=30
)
_BODIES = st.lists(_LINES, min_size=1, max_size=6).filter(
    lambda lines: any(line.strip() for line in lines) and not any(line.startswith("===") for line in lines)
)


@given(st.dictionaries(_PATHS, _BODIES, min_size=1, max_size=4))
def test_render_then_parse_round_trips(files: dict[str, list[str]]) -> None:
    blocks = [FileBlock(path, "\n".join(lines) + "\n") for path, lines in files.items()]
    assert parse_files(render_files(blocks)) == blocks


@given(st.text(max_size=300))
def test_arbitrary_text_never_raises_anything_but_envelope_error(reply: str) -> None:
    with contextlib.suppress(EnvelopeError):
        parse_files(reply)
