"""Verification ladder runner (architecture §13, Phase 0).

Public surface
--------------
:func:`run_ladder`   Run V0–V2 in sequence; returns one :class:`LevelResult` per level.
:func:`run_v0`       Syntax-only check for every source file.
:func:`run_v1`       Assemble each source to an object file.
:func:`run_v2`       Link all object files into an executable.
"""

from barthelona.verification.ladder import run_ladder, run_v0, run_v1, run_v2

__all__ = [
    "run_ladder",
    "run_v0",
    "run_v1",
    "run_v2",
]
