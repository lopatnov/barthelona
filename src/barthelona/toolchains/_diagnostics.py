"""Shared parser for ``file:line: severity: message`` assembler output.

NASM and GNU as both print this shape (architecture §13). The fixtures under
``tests/fixtures/diagnostics/`` hold the real captured output the parser is
tested against (AGENTS.md testing policy).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from barthelona.domain.enums import DiagnosticLevel
from barthelona.domain.verification import Diagnostic, Severity

_LINE = re.compile(
    r"^(?P<file>[^:\s][^:]*):(?P<line>\d+): "
    r"(?P<severity>fatal|error|warning|note): (?P<message>.+)$",
    re.IGNORECASE,
)
# NASM appends the warning class, e.g. "[-w+label-orphan]".
_NASM_CODE = re.compile(r"\[(?P<code>-w[^\]]+)\]$")
_SEVERITY: dict[str, Severity] = {
    "fatal": Severity.FATAL,
    "error": Severity.FATAL,  # an assembler error leaves no object file, so it blocks the level
    "warning": Severity.WARNING,
    "note": Severity.NOTE,
}
_NUMBER_OR_QUOTED = re.compile(r"\d+|`[^']*'|'[^']*'|\"[^\"]*\"")


def error_signature(tool: str, message: str) -> str:
    """Hash *message* with numbers and quoted symbols removed, for stall detection."""
    normalized = _NUMBER_OR_QUOTED.sub("_", message.lower())
    return hashlib.sha256(f"{tool}:{normalized}".encode()).hexdigest()


def parse_assembler_output(tool: str, output: bytes) -> list[Diagnostic]:
    """Parse *output* (stderr of nasm or as) into diagnostics; unmatched lines are skipped.

    The level is a placeholder: the ladder stamps the real one on each diagnostic.
    """
    diagnostics: list[Diagnostic] = []
    for raw_line in output.decode("utf-8", errors="replace").splitlines():
        match = _LINE.match(raw_line.strip())
        if match is None:
            continue
        message = match["message"]
        code_match = _NASM_CODE.search(message)
        code = None
        if code_match is not None:
            code = code_match["code"]
            message = message[: code_match.start()].rstrip()
        diagnostics.append(
            Diagnostic(
                tool=tool,
                level=DiagnosticLevel.V0,
                severity=_SEVERITY[match["severity"].lower()],
                code=code,
                message=message,
                file=PurePosixPath(match["file"]).name,
                line=int(match["line"]),
                error_sig=error_signature(tool, message),
            )
        )
    return diagnostics
