"""Fingerprint of the dependency declaration in pyproject.toml and of the lock files built from it.

`scripts/lock.ps1` stores it in requirements/pyproject-deps.sha256 after locking. `scripts/doctor.ps1`,
the SessionStart hook and tests/unit/test_package.py compare it, so a dependency change without a re-lock,
or a hand-edited lock, is detected, while unrelated pyproject edits (tool config) are not flagged.

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
LOCKS = ("runtime.win.lock", "dev.win.lock", "runtime.linux.lock", "dev.linux.lock")


def fingerprint() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    locks = {}
    for name in LOCKS:
        path = ROOT / "requirements" / name
        # Hash normalized text so a CRLF/LF checkout difference does not count as a change.
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.is_file() else ""
        locks[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    decl = {
        "requires-python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "optional-dependencies": project.get("optional-dependencies", {}),
        "locks": locks,
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
        print(
            "locks are STALE: pyproject.toml dependencies or a lock file changed since the last "
            "scripts/lock.ps1 (never edit locks by hand)"
        )
        return 1
    print(fp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
