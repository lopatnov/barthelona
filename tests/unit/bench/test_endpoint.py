"""The bake-off stops early and says why when the model server is down or lacks the model."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from barthelona.bench.endpoint import EndpointError, served_models
from barthelona.cli import app
from barthelona.llm import load_catalog
from barthelona.llm.catalog import ModelTarget

BENCH = Path(__file__).resolve().parents[3] / "bench"
CATALOG = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


def _local_target() -> ModelTarget:
    catalog = load_catalog(CATALOG)
    return catalog.resolve("worker", "local-only")[0]


async def test_a_refused_connection_names_the_endpoint() -> None:
    target = _local_target()
    dead = target.model_copy(
        update={"provider": target.provider.model_copy(update={"base_url": "http://127.0.0.1:1/v1"})}
    )
    with pytest.raises(EndpointError, match=r"127\.0\.0\.1:1.*server running"):
        await served_models(dead)


def test_run_stops_before_any_task_when_the_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(target: ModelTarget) -> list[str]:
        raise EndpointError("lmstudio at http://127.0.0.1:1234/v1 did not list its models")

    monkeypatch.setattr("barthelona.cli.bench.served_models", down)
    outcome = CliRunner().invoke(app, ["bench", "run", "--bench-root", str(BENCH), "--catalog", str(CATALOG)])
    assert outcome.exit_code == 2
    assert "did not list its models" in outcome.output


def test_run_stops_when_the_model_is_not_served(monkeypatch: pytest.MonkeyPatch) -> None:
    async def other(target: ModelTarget) -> list[str]:
        return ["some-other-model"]

    monkeypatch.setattr("barthelona.cli.bench.served_models", other)
    outcome = CliRunner().invoke(app, ["bench", "run", "--bench-root", str(BENCH), "--catalog", str(CATALOG)])
    assert outcome.exit_code == 2
    assert "some-other-model" in outcome.output
    assert "load it first" in outcome.output


def test_models_lists_what_each_local_endpoint_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    async def serving(target: ModelTarget) -> list[str]:
        return ["alpha", "beta"]

    monkeypatch.setattr("barthelona.cli.bench.served_models", serving)
    outcome = CliRunner().invoke(app, ["bench", "models", "--catalog", str(CATALOG)])
    assert outcome.exit_code == 0
    assert "alpha, beta" in outcome.output


def test_models_reports_a_down_endpoint_without_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(target: ModelTarget) -> list[str]:
        raise EndpointError("unreachable")

    monkeypatch.setattr("barthelona.cli.bench.served_models", down)
    outcome = CliRunner().invoke(app, ["bench", "models", "--catalog", str(CATALOG)])
    assert outcome.exit_code == 0
    assert "down (unreachable)" in outcome.output
