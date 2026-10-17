"""Strict parser for the whole-file envelope (docs/architecture.md §16.3, invariant 5).

    === FILE: src/str.asm ===
    ...file text...
    === END ===

Prose outside the blocks is ignored. Every problem is collected, so one repair prompt can list them all.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from barthelona.domain._base import RelPath

_START = re.compile(r"^=== FILE: (?P<path>.+?) ===$")
_END = "=== END ==="
_FENCE = re.compile(r"^\s*```")
_MAX_REPORTED = 10
_REL_PATH = TypeAdapter(RelPath)


@dataclass(frozen=True)
class FileBlock:
    path: str
    content: str  # LF line endings, one trailing newline


class EnvelopeError(ValueError):
    """The reply is not a valid set of FILE blocks; `errors` holds up to 10 messages for the repair prompt."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors[:_MAX_REPORTED])
        super().__init__("; ".join(self.errors))


def _path_error(path: str, write_scope: Sequence[str] | None) -> str | None:
    try:
        _REL_PATH.validate_python(path)
    except ValidationError as exc:
        return f"{path!r}: {exc.errors()[0]['msg']}"
    if write_scope is not None and not any(fnmatch.fnmatchcase(path, pattern) for pattern in write_scope):
        return f"{path!r} is outside the write scope"
    return None


def _content_error(path: str, lines: list[str]) -> str | None:
    if not any(line.strip() for line in lines):
        return f"{path!r}: empty file"
    if any(_FENCE.match(line) for line in (lines[0], lines[-1])):
        return f"{path!r}: remove the markdown code fence inside the FILE block"
    return None


def _close(
    path: str, body: list[str], files: dict[str, str], errors: list[str], write_scope: Sequence[str] | None
) -> None:
    problem = _path_error(path, write_scope) or _content_error(path, body or [""])
    if problem is None and path in files:
        problem = f"{path!r} appears twice"
    if problem:
        errors.append(problem)
    else:
        files[path] = "\n".join(body) + "\n"


def parse_files(reply: str, write_scope: Sequence[str] | None = None) -> list[FileBlock]:
    """The FILE blocks of *reply*, in order; raises `EnvelopeError` unless every block is valid."""
    errors: list[str] = []
    files: dict[str, str] = {}
    open_path: str | None = None
    body: list[str] = []
    for line in reply.replace("\r\n", "\n").split("\n"):
        start = _START.match(line)
        if open_path is None:
            if start:
                open_path, body = start["path"], []
        elif line == _END:
            _close(open_path, body, files, errors, write_scope)
            open_path = None
        elif start:
            errors.append(f"{open_path!r}: missing '{_END}' before the next FILE block")
            open_path, body = start["path"], []
        else:
            body.append(line)
    if open_path is not None:
        errors.append(f"{open_path!r}: missing '{_END}' (reply cut off?)")
    if not files and not errors:
        errors.append("no '=== FILE: <path> ===' block found")
    if errors:
        raise EnvelopeError(errors)
    return [FileBlock(path, content) for path, content in files.items()]


def render_files(files: Sequence[FileBlock]) -> str:
    """The envelope text for *files* (prompts that show the model its own earlier output use this)."""
    return "".join(
        f"=== FILE: {f.path} ===\n{f.content}{'' if f.content.endswith(chr(10)) else chr(10)}{_END}\n"
        for f in files
    )
