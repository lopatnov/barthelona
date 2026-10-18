"""Dialect adapter protocol (architecture §12, §13).

A :class:`DialectAdapter` knows how to invoke one assembler family and
parse its diagnostic output.  The adapter returns argv tuples; the
verification runner wraps them in ``docker exec <container>`` and
dispatches through the :class:`~barthelona.executors.protocol.Executor`.

Diagnostics parsers are tested against real captured tool output in
``tests/fixtures/diagnostics/<tool>/<version>/`` (AGENTS.md testing policy).
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

from barthelona.domain.enums import ObjFormat
from barthelona.domain.verification import Diagnostic


def include_dir(source: str) -> str:
    """The directory of *source* with a trailing slash, for the assembler's ``-I`` flag.

    ``docker exec`` starts in the image's ``/work``, not in the attempt's directory, so
    ``%include "gen/x.inc"`` and ``.include "gen/x.inc"`` only resolve with an explicit
    include path (NASM manual 3.02, ``-I`` option; GNU as ``-I``). NASM needs the trailing slash.
    """
    return f"{PurePosixPath(source).parent}/"


@runtime_checkable
class DialectAdapter(Protocol):
    """Assembler command builder and diagnostics parser for one dialect family."""

    @property
    def dialect_name(self) -> str:
        """The :class:`~barthelona.domain.enums.Dialect` value this adapter handles."""
        ...

    @property
    def file_extension(self) -> str:
        """Primary source file extension (e.g. ``".asm"`` or ``".s"``)."""
        ...

    def syntax_check_argv(self, source: str) -> tuple[str, ...]:
        """V0: argv for a syntax-only pass that produces no output file.

        The returned tuple must start with the tool name, e.g.
        ``("nasm", "-o", "/dev/null", source)``.  The caller prepends
        ``("docker", "exec", container)`` before dispatching.
        """
        ...

    def assemble_argv(
        self,
        source: str,
        output: str,
        obj_format: ObjFormat = ObjFormat.ELF64,
    ) -> tuple[str, ...]:
        """V1: argv to assemble *source* into *output* (an object file).

        The returned tuple must start with the tool name.
        """
        ...

    def parse_diagnostics(
        self,
        stdout: bytes,
        stderr: bytes,
        source: str,
    ) -> list[Diagnostic]:
        """Parse raw assembler output into :class:`Diagnostic` instances.

        The ladder stamps the real :class:`DiagnosticLevel` on each result.
        """
        ...
