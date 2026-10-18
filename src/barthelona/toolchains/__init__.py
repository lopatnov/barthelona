"""Toolchain discovery, lock file and dialect adapters (architecture §12, Phase 0).

``barthelona probe`` calls :func:`run_probe` to interrogate the ``bart-tc``
container, then :func:`write_lock_file` to persist the result.

Public surface
--------------
:class:`ToolInfo`         Version and path of a single tool inside the container.
:class:`ToolchainLock`    The complete lock produced by a probe run.
:func:`run_probe`         Run the full probe and return an unpersisted lock.
:func:`probe_tools`       Probe individual tool versions/paths.
:func:`probe_image_digest` Return the Docker image digest for a named image.
:func:`parse_assembler_output` Turn a tool's stderr into diagnostics.
:func:`write_lock_file`   Persist a :class:`ToolchainLock` to JSON.
:func:`read_lock_file`    Load a :class:`ToolchainLock` from JSON.

Dialect adapters
----------------
:class:`DialectAdapter`   Structural protocol for assembler command builders.
:class:`NasmAdapter`      NASM (Intel syntax macro assembler).
:class:`GasIntelAdapter`  GAS with Intel syntax (``-msyntax=intel``).
:class:`GasAttAdapter`    GAS with AT&T syntax.
"""

from barthelona.toolchains._diagnostics import parse_assembler_output
from barthelona.toolchains._types import ToolchainLock, ToolInfo
from barthelona.toolchains.dialect import DialectAdapter
from barthelona.toolchains.gas import GasAttAdapter, GasIntelAdapter
from barthelona.toolchains.nasm import NasmAdapter
from barthelona.toolchains.probe import (
    probe_image_digest,
    probe_tools,
    read_lock_file,
    run_probe,
    write_lock_file,
)

__all__ = [
    "DialectAdapter",
    "GasAttAdapter",
    "GasIntelAdapter",
    "NasmAdapter",
    "ToolInfo",
    "ToolchainLock",
    "parse_assembler_output",
    "probe_image_digest",
    "probe_tools",
    "read_lock_file",
    "run_probe",
    "write_lock_file",
]
