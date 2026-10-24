"""The demos/<name> folder choice of the New request page: taken names and whether a new one is fine."""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from barthelona.domain.project import Slug

DEMOS_DIR = Path("demos")
_SLUG = TypeAdapter(Slug)  # the same rule as Run.project, so the page never accepts a name the model rejects
_NAME_RULE = (
    "Use lowercase letters, digits and hyphens, starting with a letter or digit (at most 64 characters)."
)


def existing_projects(demos_dir: Path = DEMOS_DIR) -> list[str]:
    """The subfolders of *demos_dir*, sorted; they are taken and a run must not write into them."""
    if not demos_dir.is_dir():
        return []
    folders = (entry.name for entry in demos_dir.iterdir() if entry.is_dir())
    return sorted(name for name in folders if not name.startswith("."))


def project_problem(name: str, taken: list[str]) -> str | None:
    """What is wrong with the new folder name *name*, or None (an empty name means no folder was chosen)."""
    if not name:
        return None
    try:
        _SLUG.validate_python(name)
    except ValidationError:
        return _NAME_RULE
    if name in taken:
        return f"demos/{name} already exists; pick a new name."
    return None
