"""`python -m barthelona` entry point."""

from __future__ import annotations

import json
import subprocess
import sys

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
