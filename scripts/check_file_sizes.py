"""Fail CI when a Python source file grows too big (AGENTS.md "Code size limits").

Counts code lines only: blank lines, comments and docstrings are free. Tests are not limited.
Soft limit: warning (refactor soon). Hard limit: error (exit 1).

    python scripts/check_file_sizes.py [--soft N] [--hard N] [paths...]
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

SOFT_LIMIT = 250
HARD_LIMIT = 400
DEFAULT_ROOTS = ("src", "scripts")
_NON_CODE = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENDMARKER,
}


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def count_code_lines(source: str) -> int:
    """Number of physical lines holding code (not blank, comment-only or docstring)."""
    docstrings = _docstring_lines(ast.parse(source))
    code: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in _NON_CODE:
            continue
        code.update(range(tok.start[0], tok.end[0] + 1))
    return len(code - docstrings)


def python_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--soft", type=int, default=SOFT_LIMIT)
    parser.add_argument("--hard", type=int, default=HARD_LIMIT)
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_ROOTS))
    args = parser.parse_args(argv)

    failed = False
    for path in python_files(args.paths):
        count = count_code_lines(path.read_text(encoding="utf-8"))
        if count > args.hard:
            print(f"ERROR {path}: {count} code lines > hard limit {args.hard}")
            failed = True
        elif count > args.soft:
            print(f"warning {path}: {count} code lines > soft limit {args.soft}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
