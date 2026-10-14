"""Persistence for `var/app.sqlite` (docs/architecture.md §18): connections, migrations, the store.

The engine worker and the UI meet only here (invariant 8): the UI writes runs and commands and reads
events and gates; the worker owns everything else.
"""

from __future__ import annotations

from pathlib import Path

from barthelona.persistence.connection import connect, connect_readonly
from barthelona.persistence.migrations import LATEST_VERSION, migrate, schema_version
from barthelona.persistence.store import MAX_PAYLOAD_BYTES, ConflictError, NotFoundError, Store


def open_store(path: Path) -> Store:
    """Open the database read-write, bring its schema up to date and return a store over it."""
    conn = connect(path)
    migrate(conn)
    return Store(conn)


__all__ = [
    "LATEST_VERSION",
    "MAX_PAYLOAD_BYTES",
    "ConflictError",
    "NotFoundError",
    "Store",
    "connect",
    "connect_readonly",
    "migrate",
    "open_store",
    "schema_version",
]
