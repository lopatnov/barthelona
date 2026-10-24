"""Publish the product's SQLite stores to Zetaris so run history and memory can be queried with SQL there.

SQLite stays the engine's store (invariant 8). This copies tables to CSV, puts the files in the Zetaris
container's shared volume and registers each as a filestore table once; later publishes only refresh the files
(a filestore table reads its CSV when queried). The CSVs hold run statistics and recalled facts only.
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from barthelona.llm.zetaris import ZetarisConfig, ZetarisError, register, run_sql

DATABASE = "barthelona_runtime"
REMOTE_DIR = "/home/zetaris/customer-data/shared/barthelona_runtime"


@dataclass(frozen=True)
class Source:
    """One SQLite table published as ``<Zetaris table>``."""

    sqlite_path: Path
    sqlite_table: str
    zetaris_table: str


def default_sources(runs_db: Path, hmem_db: Path) -> tuple[Source, ...]:
    return (
        Source(runs_db, "runs", "runs"),
        Source(runs_db, "run_chunks", "run_chunks"),
        Source(hmem_db, "memories", "memories"),
        Source(hmem_db, "ledger", "memory_ledger"),
    )


def export_csv(source: Source, out_dir: Path) -> Path:
    """Dump one table with its header to ``out_dir/<zetaris table>.csv``; ZetarisError if it is missing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{source.zetaris_table}.csv"
    db = sqlite3.connect(f"file:{source.sqlite_path}?mode=ro", uri=True)
    try:
        cursor = db.execute(f'SELECT * FROM "{source.sqlite_table}"')  # noqa: S608 - names come from default_sources
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(column[0] for column in cursor.description)
            writer.writerows(cursor)
    except sqlite3.Error as exc:
        raise ZetarisError(f"cannot export {source.sqlite_table} from {source.sqlite_path}: {exc}") from exc
    finally:
        db.close()
    return target


def copy_into_container(files: Sequence[Path], container: str) -> None:
    """``docker cp`` each file into the shared volume; relative paths, since ``C:`` reads as a container."""
    _docker(["exec", container, "mkdir", "-p", REMOTE_DIR])
    for file in files:
        _docker(["cp", f"./{file.name}", f"{container}:{REMOTE_DIR}/{file.name}"], cwd=file.parent)


def _docker(args: Sequence[str], cwd: Path | None = None) -> None:
    # which() gives the full path: on Windows ``docker`` can be a .bat shim that bare argv[0] cannot start
    docker = shutil.which("docker")
    if docker is None:
        raise ZetarisError("docker is not on PATH")
    result = subprocess.run([docker, *args], capture_output=True, text=True, cwd=cwd, check=False)  # noqa: S603
    if result.returncode != 0:
        raise ZetarisError(f"docker {args[0]} failed: {result.stderr.strip()[:200]}")


def register_missing(config: ZetarisConfig, tables: Sequence[str]) -> list[str]:
    """Create the database if needed and every table not yet registered; returns the tables created."""
    known = {row[0] for row in _rows(config, "SHOW LIGHTNING DATABASES")}
    if DATABASE not in known:
        register(config, f'CREATE LIGHTNING DATABASE {DATABASE} DESCRIBE BY "Barthelona run data"')
    present = {row[0] for row in _rows(config, f"SHOW LIGHTNING TABLES {DATABASE}")}
    created = []
    for table in tables:
        if table not in present:
            register(
                config,
                f"CREATE LIGHTNING FILESTORE TABLE {table} FROM {DATABASE} FORMAT CSV OPTIONS "
                f'(path "{REMOTE_DIR}/{table}.csv", header "true", delimiter ",")',
            )
            created.append(table)
    return created


def _rows(config: ZetarisConfig, sql: str) -> tuple[tuple[str, ...], ...]:
    try:
        return run_sql(config, sql, 1000).rows
    except ZetarisError:
        return ()
