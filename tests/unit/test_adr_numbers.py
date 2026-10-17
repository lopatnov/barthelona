"""ADR numbers are unique and every ADR file has a row in docs/adr/README.md."""

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
FILE_RE = re.compile(r"^(D-\d{3})-.+\.md$")


def _adr_files() -> list[tuple[str, str]]:
    matches = (FILE_RE.match(p.name) for p in sorted(ADR_DIR.glob("D-*.md")))
    return [(m.group(1), m.group(0)) for m in matches if m]


def test_adr_numbers_are_unique() -> None:
    seen: dict[str, str] = {}
    for number, name in _adr_files():
        assert number not in seen, f"{number} is used by both {seen[number]} and {name}"
        seen[number] = name


def test_every_adr_file_is_listed_in_readme() -> None:
    readme = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    for _, name in _adr_files():
        assert f"({name})" in readme, f"{name} has no row in docs/adr/README.md"
