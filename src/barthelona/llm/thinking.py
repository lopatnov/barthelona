"""Removal of reasoning blocks that local and Qwen models put into the visible content."""

from __future__ import annotations

import re

_CLOSED_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CLOSING = "</think>"


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
