"""SQLite artifact helpers."""

import sqlite3
from pathlib import Path


def apply_schema(connection: sqlite3.Connection, schema_path: Path) -> None:
    """Apply a dataset schema as one SQLite script."""
    connection.executescript(schema_path.read_text(encoding="utf-8"))
