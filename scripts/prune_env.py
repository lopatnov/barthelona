"""Uninstall packages that are installed in the current environment but not listed in a lock file.

Used by scripts/create_env.ps1 / create_env.sh after installing a lock, so that switching
`-Deps dev` -> `runtime` or re-locking without a package leaves the env exactly as the lock says.
Never touches pip, setuptools, wheel or the barthelona package itself.

Usage: python scripts/prune_env.py <lockfile> [--dry-run]
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

KEEP = {"pip", "setuptools", "wheel", "barthelona"}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_names(lock: Path) -> set[str]:
    names = set()
    for line in lock.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", line)
        if m:
            names.add(canonical(m.group(1)))
    return names


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    lock = Path(argv[0])
    want = locked_names(lock)
    if not want:
        print(f"no pinned packages found in {lock}; refusing to prune")
        return 1
    installed = {canonical(d.metadata["Name"]) for d in metadata.distributions() if d.metadata["Name"]}
    extras = sorted(installed - want - KEEP)
    if not extras:
        print("environment matches the lock (nothing to prune)")
        return 0
    print("not in lock, removing: " + ", ".join(extras))
    if "--dry-run" in argv:
        return 0
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "--disable-pip-version-check", *extras]
    # argv list from sys.executable + names read from installed package metadata; no shell involved.
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
