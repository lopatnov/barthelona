"""Deterministic project scaffolding beyond contract codegen (D-048)."""

from barthelona.scaffold.ci import (
    DEFAULT_REQUIRED_LEVELS,
    LINUX_X64,
    UnsupportedCiTarget,
    build_commands,
    ci_family,
    render_ci,
    render_golden_ci,
)
from barthelona.scaffold.package import PackageError, package_run, target_folder
from barthelona.scaffold.project import render_project

__all__ = [
    "DEFAULT_REQUIRED_LEVELS",
    "LINUX_X64",
    "PackageError",
    "UnsupportedCiTarget",
    "build_commands",
    "ci_family",
    "package_run",
    "render_ci",
    "render_golden_ci",
    "render_project",
    "target_folder",
]
