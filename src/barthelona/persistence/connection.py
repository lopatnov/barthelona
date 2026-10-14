"""SQLite connections for `var/app.sqlite` (docs/architecture.md §17, §18; ADR D-005).

One writer (the worker) and many readers (the UI, the CLI) share the file through WAL mode.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from barthelona.persistence.migrations import LATEST_VERSION, schema_version

BUSY_TIMEOUT_MS = 5_000


def connect(path: Path) -> sqlite3.Connection:
    """Open a read-write connection in WAL mode, creating the file and its directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    _configure(conn)
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if mode != "wal":
        conn.close()
        raise RuntimeError(f"{path}: SQLite kept journal_mode={mode!r}; WAL is required (§17)")
    conn.execute("PRAGMA synchronous = NORMAL")  # durable in WAL mode except on power loss
    return conn


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open a read-only connection, safe to share across Streamlit threads (§17).

    The worker migrates the database; a reader refuses a schema it was not built for.
    """
    if not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")
    conn = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,
        check_same_thread=False,
    )
    _configure(conn)
    version = schema_version(conn)
    if version != LATEST_VERSION:
        conn.close()
        raise RuntimeError(f"{path}: schema version {version}, this barthelona reads {LATEST_VERSION}")
    return conn


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
