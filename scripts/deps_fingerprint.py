"""Fingerprint of the dependency declaration in pyproject.toml.

`scripts/lock.ps1` stores it in requirements/pyproject-deps.sha256 after locking. `scripts/doctor.ps1`,
the SessionStart hook and tests/unit/test_package.py compare it, so a dependency change without a
re-lock is detected, while unrelated pyproject edits (tool config) are not flagged.

Usage: python scripts/deps_fingerprint.py [--write | --check]
"""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / "requirements" / "pyproject-deps.sha256"


def fingerprint() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    decl = {
        "requires-python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "optional-dependencies": project.get("optional-dependencies", {}),
    }
    blob = json.dumps(decl, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main(argv: list[str]) -> int:
    fp = fingerprint()
    if "--write" in argv:
        STAMP.write_text(fp + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {STAMP.relative_to(ROOT)}")
        return 0
    if "--check" in argv:
        stored = STAMP.read_text(encoding="utf-8").strip() if STAMP.is_file() else ""
        if stored == fp:
            print("locks match pyproject.toml dependencies")
            return 0
        print("locks are STALE: dependencies in pyproject.toml changed since the last scripts/lock.ps1")
        return 1
    print(fp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
