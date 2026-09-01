"""Build the schema v2 multi-table laboratory SQLite artifact."""

import sqlite3
from dataclasses import astuple
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_database
from cn_health_compiler.sources.laboratory.records import LaboratoryCatalog
from cn_health_compiler.sources.laboratory.validation import (
    LaboratoryValidationReport,
    LaboratoryValidationRules,
    validate_laboratory_catalog,
)

_SEARCH_SQL = (
    """
    INSERT INTO laboratory_test_fts(rowid, name, analyte, category)
    SELECT rowid, name, analyte, category FROM laboratory_test ORDER BY code
    """,
    """
    WITH RECURSIVE grams(code, text, position) AS (
        SELECT code, name, 1 FROM laboratory_test WHERE length(name) >= 2
        UNION ALL SELECT code, text, position + 1 FROM grams WHERE position < length(text) - 1
    )
    INSERT OR IGNORE INTO laboratory_test_search_bigram(term, code)
    SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2
    """,
    """
    INSERT INTO laboratory_panel_fts(rowid, name)
    SELECT rowid, name FROM laboratory_panel ORDER BY code
    """,
    """
    WITH RECURSIVE grams(code, text, position) AS (
        SELECT code, name, 1 FROM laboratory_panel WHERE length(name) >= 2
        UNION ALL SELECT code, text, position + 1 FROM grams WHERE position < length(text) - 1
    )
    INSERT OR IGNORE INTO laboratory_panel_search_bigram(term, code)
    SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2
    """,
    "INSERT INTO laboratory_test_fts(laboratory_test_fts) VALUES('optimize')",
    "INSERT INTO laboratory_panel_fts(laboratory_panel_fts) VALUES('optimize')",
)


def build_laboratory_sqlite(
    catalog: LaboratoryCatalog,
    rules: LaboratoryValidationRules,
    schema_path: Path,
    output_path: Path,
    *,
    terminology_count: int,
    evidence_names: dict[int, str],
) -> SQLiteArtifact[LaboratoryValidationReport]:
    def populate(connection: sqlite3.Connection) -> LaboratoryValidationReport:
        report = validate_laboratory_catalog(
            catalog,
            rules,
            terminology_count=terminology_count,
            evidence_names=evidence_names,
        )
        connection.executemany(
            "INSERT INTO laboratory_test VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (astuple(record) for record in catalog.tests),
        )
        connection.executemany(
            "INSERT INTO laboratory_reference VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (astuple(record) for record in catalog.references),
        )
        connection.executemany(
            "INSERT INTO laboratory_panel VALUES (?, ?, ?, ?, ?, ?, ?)",
            (astuple(record) for record in catalog.panels),
        )
        connection.executemany(
            "INSERT INTO laboratory_panel_member VALUES (?, ?, ?)",
            (astuple(record) for record in catalog.panel_members),
        )
        for statement in _SEARCH_SQL:
            connection.execute(statement)
        return report

    return build_sqlite_database(schema_path, output_path, populate, user_version=2)
