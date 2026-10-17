"""Verification ladder runner (architecture §13, D-046).

Public surface
--------------
:func:`run_ladder`      Walk the registered checks of a target family up to a level.
:func:`dod_satisfied`   Definition of Done: every required level passed.
:class:`CheckRegistry`  Checks keyed by target family and level.
:func:`run_v0`, :func:`run_v1`, :func:`run_v2`, :func:`run_v5`, :func:`run_v6`
                        The native-asm level implementations.
"""

from barthelona.verification.golden import run_v6
from barthelona.verification.harness import run_v5
from barthelona.verification.ladder import (
    LadderOptions,
    default_registry,
    dod_satisfied,
    levels_through,
    run_ladder,
)
from barthelona.verification.native_asm import run_v0, run_v1, run_v2
from barthelona.verification.registry import CheckRegistry, LadderContext, LevelCheck, Unsupported

__all__ = [
    "CheckRegistry",
    "LadderContext",
    "LadderOptions",
    "LevelCheck",
    "Unsupported",
    "default_registry",
    "dod_satisfied",
    "levels_through",
    "run_ladder",
    "run_v0",
    "run_v1",
    "run_v2",
    "run_v5",
    "run_v6",
]
