"""Deterministic project scaffolding beyond contract codegen (D-048)."""

from barthelona.scaffold.ci import (
    DEFAULT_REQUIRED_LEVELS,
    LINUX_X64,
    UnsupportedCiTarget,
    ci_family,
    render_ci,
)

__all__ = ["DEFAULT_REQUIRED_LEVELS", "LINUX_X64", "UnsupportedCiTarget", "ci_family", "render_ci"]
