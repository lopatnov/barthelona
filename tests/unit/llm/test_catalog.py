"""Unit tests for the model catalog loader (config/models.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.llm import CatalogError, load_catalog
from barthelona.llm.catalog import expand_env

REPO = Path(__file__).resolve().parents[3]


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


_MINIMAL = """
providers:
  lmstudio: {kind: openai_chat, base_url: "${LM_URL:-http://127.0.0.1:1234/v1}", local: true}
  cloud: {kind: anthropic_messages, api_key_env: KEY}
models:
  local_main: {provider: lmstudio, model: m, price_class: local, context: 16384}
  big: {provider: cloud, model: b, price_class: flagship, context: 1000}
profiles:
  p:
    worker:
      - {model: big, effort: high}
      - local_main
default_profile: p
"""


def test_the_shipped_catalog_loads_and_every_chain_ends_local() -> None:
    catalog = load_catalog(REPO / "config" / "models.yaml", env={})
    for profile in catalog.profiles:
        for role in catalog.profiles[profile]:
            assert catalog.resolve(role, profile)[-1].provider.local


def test_base_url_default_and_override(tmp_path: Path) -> None:
    path = _write(tmp_path, _MINIMAL)
    default = load_catalog(path, env={})
    override = load_catalog(path, env={"LM_URL": "http://127.0.0.1:9/v1"})
    assert default.providers["lmstudio"].base_url == "http://127.0.0.1:1234/v1"
    assert override.providers["lmstudio"].base_url == "http://127.0.0.1:9/v1"


def test_resolve_keeps_order_and_per_role_params(tmp_path: Path) -> None:
    catalog = load_catalog(_write(tmp_path, _MINIMAL), env={})
    chain = catalog.resolve("worker")
    assert [t.key for t in chain] == ["big", "local_main"]
    assert chain[0].params == {"effort": "high"}


def test_unknown_role_is_an_error(tmp_path: Path) -> None:
    catalog = load_catalog(_write(tmp_path, _MINIMAL), env={})
    with pytest.raises(CatalogError, match="role 'planner'"):
        catalog.resolve("planner")


def test_chain_must_end_in_a_local_model(tmp_path: Path) -> None:
    text = _MINIMAL.replace("      - local_main\n", "")
    with pytest.raises(CatalogError, match="must end in a local model"):
        load_catalog(_write(tmp_path, text), env={})


def test_chain_with_unknown_model_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="unknown model 'ghost'"):
        load_catalog(_write(tmp_path, _MINIMAL.replace("local_main\ndefault", "ghost\ndefault")), env={})


def test_localhost_is_rejected_for_local_providers(tmp_path: Path) -> None:
    text = _MINIMAL.replace("http://127.0.0.1:1234/v1", "http://localhost:1234/v1")
    with pytest.raises(CatalogError, match=r"127\.0\.0\.1"):
        load_catalog(_write(tmp_path, text), env={})


def test_unreadable_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="cannot read"):
        load_catalog(tmp_path / "missing.yaml", env={})


@pytest.mark.parametrize(
    ("value", "env", "expected"),
    [
        ("${A}", {"A": "x"}, "x"),
        ("${A:-d}/v1", {}, "d/v1"),
        ("${A:-d}", {"A": ""}, "d"),
        ("${A}", {}, ""),
        ("plain", {}, "plain"),
    ],
)
def test_expand_env(value: str, env: dict[str, str], expected: str) -> None:
    assert expand_env(value, env) == expected
