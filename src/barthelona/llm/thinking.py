"""Removal of reasoning blocks that local and Qwen models put into the visible content."""

from __future__ import annotations

import re

_CLOSED_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """Drop `<think>...</think>` blocks; an unterminated block (output cut off mid-thought) goes too."""
    without_closed = _CLOSED_BLOCK.sub("", text)
    opening = without_closed.find("<think>")
    if opening != -1:
        without_closed = without_closed[:opening]
    return without_closed.strip()
