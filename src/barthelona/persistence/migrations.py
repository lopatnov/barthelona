"""Schema migrations for `var/app.sqlite`, tracked with `PRAGMA user_version`.

Migrations are append-only: a released migration is never edited; a change is a new entry. Tables for
later features (lessons, overlay changes, policy pointer, metrics, bench results, exec log) arrive with
those features (docs/architecture.md §18).
"""

from __future__ import annotations

import sqlite3

# Each entry is one migration; its 1-based position is the schema version it produces.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE runs (
        id          TEXT PRIMARY KEY,
        status      TEXT NOT NULL,
        stop_reason TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        doc         TEXT NOT NULL CHECK (json_valid(doc))
    ) STRICT;
    CREATE INDEX runs_status ON runs (status);

    CREATE TABLE commands (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id     TEXT NOT NULL REFERENCES runs (id),
        kind       TEXT NOT NULL,
        created_at TEXT NOT NULL,
        claimed_at TEXT,
        doc        TEXT NOT NULL CHECK (json_valid(doc))
    ) STRICT;
    CREATE INDEX commands_unclaimed ON commands (run_id, id) WHERE claimed_at IS NULL;

    CREATE TABLE events (
        run_id TEXT NOT NULL REFERENCES runs (id),
        seq    INTEGER NOT NULL CHECK (seq >= 0),
        ts     TEXT NOT NULL,
        kind   TEXT NOT NULL,
        doc    TEXT NOT NULL CHECK (json_valid(doc)),
        PRIMARY KEY (run_id, seq)
    ) STRICT, WITHOUT ROWID;

    CREATE TABLE gates (
        gate_id     TEXT PRIMARY KEY,
        run_id      TEXT NOT NULL REFERENCES runs (id),
        kind        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        resolved_at TEXT,
        request     TEXT NOT NULL CHECK (json_valid(request)),
        decision    TEXT CHECK (decision IS NULL OR json_valid(decision)),
        CHECK ((resolved_at IS NULL) = (decision IS NULL))
    ) STRICT;
    CREATE INDEX gates_pending ON gates (run_id) WHERE resolved_at IS NULL;

    CREATE TABLE llm_calls (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id     TEXT NOT NULL REFERENCES runs (id),
        provider   TEXT NOT NULL,
        model      TEXT NOT NULL,
        tokens_in  INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL,
        usd        REAL,
        created_at TEXT NOT NULL,
        doc        TEXT NOT NULL CHECK (json_valid(doc))
    ) STRICT;
    CREATE INDEX llm_calls_run ON llm_calls (run_id);
    """,
)

LATEST_VERSION = len(MIGRATIONS)


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations, each in its own transaction, and return the resulting version.

    Raises `RuntimeError` for a database written by a newer barthelona, which this code must not touch.
    """
    current = schema_version(conn)
    if current > LATEST_VERSION:
        raise RuntimeError(
            f"database schema version {current} is newer than this barthelona supports ({LATEST_VERSION})"
        )
    # In autocommit mode executescript() does not commit a pending transaction, so each step can hold
    # BEGIN IMMEDIATE across its script; the caller's transaction mode is restored afterwards.
    previous_mode = conn.autocommit
    conn.autocommit = True
    try:
        for version in range(current + 1, LATEST_VERSION + 1):
            _apply(conn, version)
    finally:
        conn.autocommit = previous_mode
    return schema_version(conn)


def _apply(conn: sqlite3.Connection, version: int) -> None:
    """Apply one migration under the write lock, unless a concurrent caller already applied it."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        if schema_version(conn) < version:
            conn.executescript(f"{MIGRATIONS[version - 1]}\nPRAGMA user_version = {version};")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
