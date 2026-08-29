"""Deterministic SQLite artifact helpers."""

import os
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from cn_health_compiler.core.source import hash_file

SQLITE_APPLICATION_ID = 0x434E4844
_BATCH_SIZE = 1000


class RecordCountReport(Protocol):
    record_count: int


class StreamingValidator[RecordT, ReportT: RecordCountReport](Protocol):
    def consume(self, record: RecordT) -> None: ...

    def finish(self) -> ReportT: ...


@dataclass(frozen=True, slots=True)
class SQLiteArtifact[ReportT: RecordCountReport]:
    path: Path
    sha256: str
    size_bytes: int
    validation: ReportT


def apply_schema(connection: sqlite3.Connection, schema_path: Path) -> None:
    """Apply a dataset schema as one SQLite script."""
    connection.executescript(schema_path.read_text(encoding="utf-8"))


def build_sqlite_artifact[RecordT, ReportT: RecordCountReport](
    records: Iterable[RecordT],
    validator: StreamingValidator[RecordT, ReportT],
    row_values: Callable[[RecordT], tuple[object, ...]],
    columns: Sequence[str],
    schema_path: Path,
    output_path: Path,
    *,
    table: str,
    staging_table: str,
    post_insert_sql: Sequence[str],
) -> SQLiteArtifact[ReportT]:
    """Validate, sort, optimize, and atomically publish one SQLite artifact."""

    def populate(connection: sqlite3.Connection) -> ReportT:
        return _populate_table(
            connection,
            records,
            validator,
            row_values,
            columns,
            table,
            staging_table,
            post_insert_sql,
        )

    return build_sqlite_database(schema_path, output_path, populate)


def build_sqlite_database[ReportT: RecordCountReport](
    schema_path: Path,
    output_path: Path,
    populate: Callable[[sqlite3.Connection], ReportT],
) -> SQLiteArtifact[ReportT]:
    """Populate and atomically publish a deterministic SQLite database."""
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite SQLite artifact: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}-",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.execute("PRAGMA page_size = 4096")
            connection.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
            connection.execute("PRAGMA user_version = 1")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA temp_store = FILE")
            apply_schema(connection, schema_path)
            connection.execute("BEGIN IMMEDIATE")
            validation = populate(connection)
            connection.commit()
            connection.execute("ANALYZE")
            connection.execute("PRAGMA optimize")
            connection.commit()
            connection.execute("VACUUM")
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
            if integrity_rows != [("ok",)]:
                raise RuntimeError(f"SQLite integrity_check failed: {integrity_rows!r}")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        _sync_file(temporary_path)
        os.replace(temporary_path, output_path)
        digest, size = hash_file(output_path)
        return SQLiteArtifact(output_path, digest, size, validation)
    finally:
        _remove_database_files(temporary_path)


def _populate_table[RecordT, ReportT: RecordCountReport](
    connection: sqlite3.Connection,
    records: Iterable[RecordT],
    validator: StreamingValidator[RecordT, ReportT],
    row_values: Callable[[RecordT], tuple[object, ...]],
    columns: Sequence[str],
    table: str,
    staging_table: str,
    post_insert_sql: Sequence[str],
) -> ReportT:
    column_list = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    staging_insert = f"INSERT INTO {staging_table} ({column_list}) VALUES ({placeholders})"
    connection.execute(f"CREATE TABLE {staging_table} AS SELECT * FROM {table} WHERE 0")
    batch: list[tuple[object, ...]] = []
    for record in records:
        validator.consume(record)
        batch.append(row_values(record))
        if len(batch) == _BATCH_SIZE:
            connection.executemany(staging_insert, batch)
            batch.clear()
    if batch:
        connection.executemany(staging_insert, batch)
    validation = validator.finish()
    connection.execute(
        f"INSERT INTO {table} ({column_list}) "
        f"SELECT {column_list} FROM {staging_table} ORDER BY code"
    )
    connection.execute(f"DROP TABLE {staging_table}")
    for statement in post_insert_sql:
        connection.execute(statement)
    return validation


def _sync_file(path: Path) -> None:
    with path.open("rb") as artifact:
        os.fsync(artifact.fileno())


def _remove_database_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in ("-journal", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
