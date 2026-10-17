"""`python -m barthelona` entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

import barthelona
from barthelona.cli import app
from barthelona.domain import DOCUMENTS

runner = CliRunner()


def test_module_entry_point_prints_the_version() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "barthelona", "version"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == barthelona.__version__


def test_schema_lists_documents() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert result.stdout.split() == sorted(DOCUMENTS)


def test_schema_prints_valid_json() -> None:
    result = runner.invoke(app, ["schema", "TopologyRequest"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["properties"]["rationale"]["maxLength"] == 300


def test_schema_rejects_unknown_document() -> None:
    result = runner.invoke(app, ["schema", "Nope"])
    assert result.exit_code != 0


def test_verify_rejects_invalid_contracts(tmp_path: Path) -> None:
    (tmp_path / "a.asm").write_text("; stub\n", encoding="utf-8")
    bad = tmp_path / "contracts.yaml"
    bad.write_text("version: 0\n", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(tmp_path), "--contracts", str(bad)])
    assert result.exit_code == 2


def test_verify_stops_on_tampered_gen(tmp_path: Path) -> None:
    (tmp_path / "a.asm").write_text("; stub\n", encoding="utf-8")
    contracts = tmp_path / "contracts.yaml"
    contracts.write_text(
        "version: 1\n"
        "target: {preset: linux-x64-test, dialect: nasm, arch: x86-64, os: linux, abi: sysv64,\n"
        "  obj_format: elf64, link: ld, run_env: docker-native}\n"
        "symbols:\n  f: {name: f, kind: func, module: src/a.asm}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["verify", str(tmp_path), "--contracts", str(contracts)])
    assert result.exit_code == 1
    assert "tamper" in result.stdout
