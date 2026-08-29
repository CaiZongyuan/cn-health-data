"""Deterministic SQLite artifact construction for NHSA drug records."""

import os
import sqlite3
from collections.abc import Iterable
from dataclasses import astuple, dataclass, fields
from pathlib import Path
from tempfile import NamedTemporaryFile

from cn_health_compiler.core.source import hash_file
from cn_health_compiler.core.sqlite import apply_schema
from cn_health_compiler.sources.nhsa_drugs.records import DrugRecord
from cn_health_compiler.sources.nhsa_drugs.validation import (
    DrugRecordValidator,
    DrugValidationRules,
    ValidationReport,
)

_APPLICATION_ID = 0x434E4844
_SCHEMA_VERSION = 1
_BATCH_SIZE = 1000
_DRUG_COLUMNS = tuple(field.name for field in fields(DrugRecord))
_COLUMN_LIST = ", ".join(_DRUG_COLUMNS)
_PLACEHOLDERS = ", ".join("?" for _ in _DRUG_COLUMNS)
_STAGING_INSERT = f"INSERT INTO drug_staging ({_COLUMN_LIST}) VALUES ({_PLACEHOLDERS})"


class SQLiteBuildError(RuntimeError):
    """Raised when a SQLite artifact fails post-build integrity checks."""


@dataclass(frozen=True, slots=True)
class SQLiteArtifact:
    """A verified SQLite artifact and its validation report."""

    path: Path
    sha256: str
    size_bytes: int
    record_count: int
    validation: ValidationReport


def build_drug_sqlite(
    records: Iterable[DrugRecord],
    rules: DrugValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact:
    """Validate records and atomically build a ready-to-query SQLite database."""
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
        validation = _populate_database(temporary_path, schema_path, records, rules)
        _sync_file(temporary_path)
        os.replace(temporary_path, output_path)
        artifact_sha256, artifact_size = hash_file(output_path)
        return SQLiteArtifact(
            path=output_path,
            sha256=artifact_sha256,
            size_bytes=artifact_size,
            record_count=validation.record_count,
            validation=validation,
        )
    finally:
        _remove_database_files(temporary_path)


def _populate_database(
    database_path: Path,
    schema_path: Path,
    records: Iterable[DrugRecord],
    rules: DrugValidationRules,
) -> ValidationReport:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA page_size = 4096")
        connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA temp_store = FILE")
        apply_schema(connection, schema_path)
        connection.execute("CREATE TABLE drug_staging AS SELECT * FROM drug WHERE 0")

        validator = DrugRecordValidator(rules)
        batch: list[tuple[object, ...]] = []
        connection.execute("BEGIN IMMEDIATE")
        for record in records:
            validator.consume(record)
            batch.append(astuple(record))
            if len(batch) == _BATCH_SIZE:
                connection.executemany(_STAGING_INSERT, batch)
                batch.clear()
        if batch:
            connection.executemany(_STAGING_INSERT, batch)

        validation = validator.finish()
        connection.execute(
            f"INSERT INTO drug ({_COLUMN_LIST}) "
            f"SELECT {_COLUMN_LIST} FROM drug_staging ORDER BY code"
        )
        connection.execute("DROP TABLE drug_staging")
        connection.execute(
            """
            INSERT INTO drug_fts(
                rowid,
                registered_name,
                trade_name,
                insurance_name,
                manufacturer
            )
            SELECT rowid, registered_name, trade_name, insurance_name, manufacturer
            FROM drug
            ORDER BY code
            """
        )
        connection.execute("INSERT INTO drug_fts(drug_fts) VALUES('optimize')")
        connection.commit()

        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.execute("VACUUM")
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        if integrity_rows != [("ok",)]:
            raise SQLiteBuildError(f"SQLite integrity_check failed: {integrity_rows!r}")
        return validation
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _sync_file(path: Path) -> None:
    with path.open("rb") as artifact:
        os.fsync(artifact.fileno())


def _remove_database_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in ("-journal", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
