"""Removal of reasoning blocks that local and Qwen models put into the visible content."""

from __future__ import annotations

import re

_CLOSED_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CLOSING = "</think>"


def think_text(text: str) -> str:
    """The reasoning that `strip_think` removes, for the optional reasoning log."""
    closed = [block[len("<think>") : -len(_CLOSING)].strip() for block in _CLOSED_BLOCK.findall(text)]
    rest = _CLOSED_BLOCK.sub("", text)
    closing = rest.rfind(_CLOSING)
    if closing != -1:
        closed.append(rest[:closing].strip())
    elif (opening := rest.find("<think>")) != -1:
        closed.append(rest[opening + len("<think>") :].strip())
    return "\n\n".join(part for part in closed if part)


def strip_think(text: str) -> str:
    """Drop `<think>...</think>` blocks; an unterminated block (output cut off mid-thought) goes too.

    A chat template that opens the thought itself leaves only the closing tag (seen live with Nemotron: the
    reasoning, then `</think>` glued to the code fence); everything up to that tag is the thought.
    """
    without_closed = _CLOSED_BLOCK.sub("", text)
    closing = without_closed.rfind(_CLOSING)
    if closing != -1:
        without_closed = without_closed[closing + len(_CLOSING) :]
    opening = without_closed.find("<think>")
    if opening != -1:
        without_closed = without_closed[:opening]
    return without_closed.strip()
