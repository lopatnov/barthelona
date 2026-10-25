"""What really bounds a run today, in words, for the form and the Live Run parameters."""

from __future__ import annotations

# Keep equal to the engine (engine/codegen.py: REPAIRS + 1 attempts, CHUNKS.max_chunks). The UI never imports
# the engine (invariant 8), so tests/unit/ui/test_bounds.py compares them.
CODE_ATTEMPTS = 5
CODE_CHUNKS = 8

REAL_BOUNDS = (
    f"Besides these limits a run makes at most {CODE_ATTEMPTS} code attempts (the first plus "
    f"{CODE_ATTEMPTS - 1} repair rounds), each of at most {CODE_CHUNKS} model calls, after one call each for "
    "understanding the request, the specification and the tests. Sprints do not exist yet."
)
