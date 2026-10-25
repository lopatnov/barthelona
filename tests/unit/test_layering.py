"""Import edges that keep the UI and the engine apart (invariant 8, D-045).

Issue #271 broke the first of them: the New Request page imported `barthelona.engine.host` for a file name and
a path join. The full sibling matrix of D-045 and its SDK containment are issue #65; these are the edges that
nothing else enforces today. Every module is parsed, never imported, so the test needs no optional tool.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "barthelona"

# D-045 gives the UI `domain`, `persistence` and `config`; F-115 (owner, 2026-10-24) adds `scaffold`, which
# renders the Package panel in the UI process. D-058 (World Model) adds `world_model`: the UI reads the same
# file-backed shared state the worker writes, without importing the engine. A new entry here is an edit of
# that table first.
UI_PACKAGES = frozenset({"domain", "persistence", "config", "scaffold", "world_model"})

# The only module above `cli`, and the only one allowed to import it.
ENTRY_POINT = "__main__"


def _modules() -> list[tuple[str, Path]]:
    """Every Python module under `src/barthelona` as (top-level package, path)."""
    return [(_package(path), path) for path in sorted(SRC.rglob("*.py")) if "__pycache__" not in path.parts]


def _package(path: Path) -> str:
    """The package a module belongs to; only `__main__.py` above the packages is the entry point."""
    parts = path.relative_to(SRC).parts
    if len(parts) == 1:
        return ENTRY_POINT if path.name == "__main__.py" else "barthelona"
    return parts[0]


def _from_names(node: ast.ImportFrom, package: tuple[str, ...]) -> set[str]:
    """The module names one `from ... import ...` reaches; a relative form is resolved against *package*."""
    if node.level:
        base = package[: max(0, len(package) - (node.level - 1))]
        parts = ["barthelona", *base, *([node.module] if node.module else [])]
        module = ".".join(parts)
        # `from .engine import x` names one module; `from . import engine` names a sub-module per alias.
        return {module} if node.module else {f"{module}.{alias.name}" for alias in node.names}
    if node.module == "barthelona":  # `from barthelona import cli`: the imported name is a package
        return {f"barthelona.{alias.name}" for alias in node.names}
    return {node.module} if node.module else set()


def _imports(path: Path) -> set[str]:
    """The absolute module names *path* imports, including the ones inside functions and methods."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.relative_to(SRC).parts[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(_from_names(node, package))
    return names


def _edges() -> dict[str, set[str]]:
    """For each top-level package, the other barthelona packages any of its modules import."""
    edges: dict[str, set[str]] = {}
    for package, path in _modules():
        reached = {name.split(".", 2)[1] for name in _imports(path) if name.startswith("barthelona.")}
        edges.setdefault(package, set()).update(reached - {package})
    return edges


def test_the_ui_imports_only_the_layers_it_may() -> None:
    ui = _edges()["ui"]
    assert ui <= UI_PACKAGES, (
        f"the UI imports {sorted(ui - UI_PACKAGES)}; it may import {sorted(UI_PACKAGES)}"
    )


def test_only_the_cli_and_the_entry_point_import_the_engine() -> None:
    offenders = sorted(
        package
        for package, reached in _edges().items()
        if package not in {"cli", ENTRY_POINT} and "engine" in reached
    )
    assert not offenders, (
        f"the UI and the engine talk through SQLite only (invariant 8); engine imported by {offenders}"
    )


def test_nothing_but_the_entry_point_imports_a_client() -> None:
    """The entry point starts the CLI; every other package, the CLI included, imports neither client."""
    offenders = sorted(
        package for package, reached in _edges().items() if package != ENTRY_POINT and reached & {"ui", "cli"}
    )
    assert not offenders, f"nothing may import a client: {offenders} import the UI or the CLI"


def test_only_the_ui_imports_streamlit() -> None:
    offenders = sorted(
        str(path.relative_to(SRC))
        for package, path in _modules()
        if package != "ui" and "streamlit" in _imports(path)
    )
    assert not offenders, f"Streamlit belongs to the UI alone; imported by {offenders}"
