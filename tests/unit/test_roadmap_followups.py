"""Follow-up ids in docs/roadmap.md are unique (the roadmap reused F-25 to F-28 once)."""

import re
from collections import Counter
from pathlib import Path

ROADMAP = Path(__file__).resolve().parents[2] / "docs" / "roadmap.md"
ROW_RE = re.compile(r"^\| (F-\d+) \|", re.MULTILINE)


def test_followup_ids_are_unique() -> None:
    ids = ROW_RE.findall(ROADMAP.read_text(encoding="utf-8"))
    assert ids, "no follow-up rows found; did the table format change?"
    duplicates = sorted(i for i, count in Counter(ids).items() if count > 1)
    assert not duplicates, f"follow-up ids used more than once: {duplicates}"
