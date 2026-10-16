"""Toolchain discovery and lock file (architecture §12, Phase 0).

``barthelona probe`` calls :func:`run_probe` to interrogate the ``bart-tc``
container, then :func:`write_lock_file` to persist the result.

Public surface
--------------
:class:`ToolInfo`       Version and path of a single tool inside the container.
:class:`ToolchainLock`  The complete lock produced by a probe run.
:func:`run_probe`       Run the full probe and return an unpersisted lock.
:func:`probe_tools`     Probe individual tool versions/paths.
:func:`probe_image_digest`  Return the Docker image digest for a named image.
:func:`write_lock_file` Persist a :class:`ToolchainLock` to JSON.
:func:`read_lock_file`  Load a :class:`ToolchainLock` from JSON.
"""

from barthelona.toolchains._types import ToolInfo, ToolchainLock
from barthelona.toolchains.probe import (
    probe_image_digest,
    probe_tools,
    read_lock_file,
    run_probe,
    write_lock_file,
)

__all__ = [
    "ToolInfo",
    "ToolchainLock",
    "probe_image_digest",
    "probe_tools",
    "read_lock_file",
    "run_probe",
    "write_lock_file",
]
