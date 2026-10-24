"""V3 and V4 against the ABI mutation corpus: every bad snippet is flagged for its kind, no good one is."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from barthelona.emulator.abi_static import lint_object
from barthelona.emulator.machine import run_function
from barthelona.emulator.object_image import load_object

CORPUS = Path(__file__).resolve().parents[2] / "abi_mutation"
_KINDS = yaml.safe_load((CORPUS / "kinds.yaml").read_text(encoding="utf-8"))
_ASSEMBLERS = {
    "nasm": ("nasm", lambda src, out: ["nasm", "-f", "elf64", "-o", out, src]),
    "gas-intel": ("as", lambda src, out: ["as", "--64", "-o", out, src]),
}
_CASES = [(dialect, kind) for dialect in _KINDS["dialects"] for kind in _KINDS["kinds"]]


def _assemble(dialect: str, source: Path, tmp_path: Path) -> bytes:
    tool, command = _ASSEMBLERS[dialect]
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} is not installed on this host; the docker job assembles the corpus")
    out = tmp_path / "probe.o"
    subprocess.run(command(str(source), str(out)), check=True, capture_output=True)
    return out.read_bytes()


def _found_kinds(blob: bytes) -> set[str]:
    image = load_object(blob)
    result = run_function(image, image.symbols["probe"], (7,))
    return {v.kind for v in lint_object(blob)} | {v.kind for v in result.violations}


def _snippet(dialect: str, verdict: str, kind: str) -> Path:
    return CORPUS / dialect / verdict / f"{kind}.{_KINDS['dialects'][dialect]}"


@pytest.mark.parametrize(("dialect", "kind"), _CASES)
def test_the_bad_snippet_is_flagged_for_its_kind(dialect: str, kind: str, tmp_path: Path) -> None:
    blob = _assemble(dialect, _snippet(dialect, "bad", kind), tmp_path)
    assert kind in _found_kinds(blob)


@pytest.mark.parametrize(("dialect", "kind"), _CASES)
def test_the_good_snippet_is_clean(dialect: str, kind: str, tmp_path: Path) -> None:
    blob = _assemble(dialect, _snippet(dialect, "good", kind), tmp_path)
    assert _found_kinds(blob) == set()
