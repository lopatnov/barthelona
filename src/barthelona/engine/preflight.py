"""Preflight (docs/architecture.md §6.1 step 2): can this host run the run's target at all?

Deterministic, no model call. Phase 1 supports the six linux-x64 NASM and GAS presets (§12); anything else
stops the run with `unsupported_target` before a gate is shown. The probed toolchain lock joins the check when
the scaffold step needs it.
"""

from __future__ import annotations

from barthelona.engine.graph import Preflight
from barthelona.persistence import Store

SUPPORTED_PRESETS = frozenset(
    f"linux-x64-{dialect}-{link}"
    for dialect in ("nasm", "gas-intel", "gas-att")
    for link in ("static", "libc")
)


def preflight_for(store: Store) -> Preflight:
    """A preflight that looks the run up in *store* and names the unsupported preset."""

    def check(run_id: str) -> str | None:
        preset = store.get_run(run_id).target.preset
        if preset in SUPPORTED_PRESETS:
            return None
        return f"preset {preset!r} is not supported yet; Phase 1 runs {', '.join(sorted(SUPPORTED_PRESETS))}"

    return check
