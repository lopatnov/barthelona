"""Shared pieces of the code generators: the output directory, the hash header and the error type."""

from __future__ import annotations

import hashlib

GEN_DIR = "gen"
HEADER_MARK = "barthelona-gen v1 body-sha256="


class CodegenError(ValueError):
    """The registry or a test case cannot be rendered."""


def stamp(comment: str, lines: list[str]) -> str:
    """Join lines into a generated file: a hash header over the body, then the body (LF only)."""
    body = "".join(f"{line}\n" for line in lines)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{comment} GENERATED from contracts.yaml, do not edit. {HEADER_MARK}{digest}\n{body}"
