"""How ``verify`` prints its ladder results: a readable list or one JSON document."""

from __future__ import annotations

import json

from rich.console import Console

from barthelona.domain import LevelResult

_out = Console(soft_wrap=True, highlight=False)
_STATUS_ICON: dict[str, str] = {"pass": "✓", "skipped": "—"}


def exit_code(results: list[LevelResult]) -> int:
    return 1 if any(r.status in ("fail", "unsupported") for r in results) else 0


def report_json(results: list[LevelResult]) -> int:
    """Print the results as one JSON document on stdout; return the process exit code."""
    code = exit_code(results)
    document = {"status": "fail" if code else "pass", "levels": [r.model_dump(mode="json") for r in results]}
    _out.print(json.dumps(document, indent=2, sort_keys=True), markup=False)
    return code


def report(results: list[LevelResult]) -> int:
    """Print each ladder level and its diagnostics; return the process exit code."""
    for r in results:
        _out.print(f"  {_STATUS_ICON.get(r.status, '✗')} {r.level}: {r.status} ({r.secs:.2f}s)")
        for d in r.diagnostics:
            loc = f"{d.file}:{d.line}" if d.file and d.line else (d.file or "")
            _out.print(f"    {d.severity} [{d.level}] {loc} {d.message}", markup=False)
    return exit_code(results)
