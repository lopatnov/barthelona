"""Prompting: output envelopes and (later) context assembly (docs/architecture.md §16.3-16.4)."""

from barthelona.prompting.envelope import EnvelopeError, FileBlock, parse_files, render_files

__all__ = ["EnvelopeError", "FileBlock", "parse_files", "render_files"]
