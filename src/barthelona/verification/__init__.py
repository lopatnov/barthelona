"""Verification ladder runner (architecture §13, D-046).

Public surface
--------------
:func:`run_ladder`      Walk the registered checks of a target family up to a level.
:func:`dod_satisfied`   Definition of Done: every level up to the bound passed.
:class:`CheckRegistry`  Checks keyed by target family and level.
:func:`run_v0`, :func:`run_v1`, :func:`run_v2`
                        The native-asm V0-V2 implementations.
"""

from barthelona.verification.ladder import default_registry, dod_satisfied, run_ladder
from barthelona.verification.native_asm import run_v0, run_v1, run_v2
from barthelona.verification.registry import CheckRegistry, LadderContext, LevelCheck, Unsupported

__all__ = [
    "CheckRegistry",
    "LadderContext",
    "LevelCheck",
    "Unsupported",
    "default_registry",
    "dod_satisfied",
    "run_ladder",
    "run_v0",
    "run_v1",
    "run_v2",
]
