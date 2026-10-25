"""Where a run's files live under `var/runs/<run_id>/` (docs/architecture.md §18).

The UI and the CLI write `request.txt` and the worker reads it, so both sides must agree on the names and
the folder. They live here, in `domain`, which every layer may import (D-045): the UI never imports the
engine (invariant 8), and `scaffold` reads the same files without reaching into it. Paths and names only;
the modules that own the files do the reading and the writing. `RUNS_DIR` is relative to the process working
directory, so the worker and the UI both start from the repository root (`scripts/run.ps1` does).
"""

from __future__ import annotations

from pathlib import Path

RUNS_DIR = Path("var/runs")
SOURCE_FILE = "main.asm"  # the source gate G4 shows and packaging copies
ATTEMPT_FILE = "attempt-{n}.asm"  # every draft of the code step, kept even when the oracles reject it
REQUEST_FILE = "request.txt"
SPEC_FILE = "spec.json"
TESTS_FILE = "tests.json"
REASONING_FILE = "reasoning.md"  # what the models thought and answered during this run; the UI shows it


def run_dir(runs_dir: Path, run_id: str) -> Path:
    """The one folder that holds a run's request, spec, tests and source."""
    return runs_dir / run_id
