"""Deterministic record-level SQLite release comparison."""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class RecordCountChangeError(ValueError):
    """Raised when a release changes size beyond its configured threshold."""


@dataclass(frozen=True, slots=True)
class DatasetDiff:
    base_count: int
    target_count: int
    added: int
    removed: int
    modified: int
    unchanged: int
    modified_fields: tuple[tuple[str, int], ...]


def compare_sqlite_tables(
    base_path: Path,
    target_path: Path,
    table: str,
    *,
    excluded_fields: tuple[str, ...] = (),
) -> DatasetDiff:
    """Compare two same-schema tables by code without loading records into memory."""
    _validate_identifier(table)
    for field_name in excluded_fields:
        _validate_identifier(field_name)
    connection = sqlite3.connect(f"file:{target_path}?mode=ro", uri=True)
    try:
        connection.execute("ATTACH DATABASE ? AS base", (str(base_path.resolve()),))
        target_columns = _columns(connection, "main", table)
        base_columns = _columns(connection, "base", table)
        if target_columns != base_columns:
            raise ValueError("base and target SQLite schemas differ")
        if "code" not in target_columns:
            raise ValueError(f"{table} has no code column")
        compared_columns = tuple(
            column
            for column in target_columns
            if column != "code" and column not in excluded_fields
        )
        condition = " OR ".join(
            f"NOT (target.{column} IS base_record.{column})" for column in compared_columns
        )
        base_count = _scalar(connection, f"SELECT count(*) FROM base.{table}")
        target_count = _scalar(connection, f"SELECT count(*) FROM main.{table}")
        added = _scalar(
            connection,
            f"SELECT count(*) FROM main.{table} AS target "
            f"LEFT JOIN base.{table} AS base_record USING(code) "
            "WHERE base_record.code IS NULL",
        )
        removed = _scalar(
            connection,
            f"SELECT count(*) FROM base.{table} AS base_record "
            f"LEFT JOIN main.{table} AS target USING(code) "
            "WHERE target.code IS NULL",
        )
        modified = (
            _scalar(
                connection,
                f"SELECT count(*) FROM main.{table} AS target "
                f"JOIN base.{table} AS base_record USING(code) WHERE {condition}",
            )
            if condition
            else 0
        )
        intersection = target_count - added
        modified_fields = _modified_field_counts(connection, table, compared_columns)
        return DatasetDiff(
            base_count=base_count,
            target_count=target_count,
            added=added,
            removed=removed,
            modified=modified,
            unchanged=intersection - modified,
            modified_fields=modified_fields,
        )
    finally:
        connection.close()


def enforce_relative_record_count(
    base_count: int,
    target_count: int,
    *,
    max_decrease: float,
    max_increase: float,
) -> None:
    if base_count <= 0:
        raise ValueError("base_count must be positive")
    change = (target_count - base_count) / base_count
    if change < -max_decrease:
        raise RecordCountChangeError(
            f"record count decreased by {-change:.2%}; maximum is {max_decrease:.2%}"
        )
    if change > max_increase:
        raise RecordCountChangeError(
            f"record count increased by {change:.2%}; maximum is {max_increase:.2%}"
        )


def _columns(connection: sqlite3.Connection, database: str, table: str) -> tuple[str, ...]:
    columns = tuple(
        str(row[1]) for row in connection.execute(f"PRAGMA {database}.table_info({table})")
    )
    for column in columns:
        _validate_identifier(column)
    return columns


def _modified_field_counts(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    if not columns:
        return ()
    expressions = ", ".join(
        f"sum(NOT (target.{column} IS base_record.{column}))" for column in columns
    )
    row = connection.execute(
        f"SELECT {expressions} FROM main.{table} AS target "
        f"JOIN base.{table} AS base_record USING(code)"
    ).fetchone()
    if row is None:
        raise RuntimeError("modified-field query returned no row")
    return tuple((column, int(count)) for column, count in zip(columns, row, strict=True) if count)


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("count query returned no row")
    return int(row[0])


def _validate_identifier(identifier: str) -> None:
    if _IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError(f"unsafe SQLite identifier: {identifier!r}")
