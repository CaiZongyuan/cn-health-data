"""SQLite artifact construction for WS/T 886."""

from collections.abc import Iterable
from dataclasses import astuple, fields
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_artifact
from cn_health_compiler.sources.nhc_lab.records import NHCLaboratoryTestRecord
from cn_health_compiler.sources.nhc_lab.validation import (
    NHCLaboratoryRecordValidator,
    NHCLaboratoryValidationReport,
    NHCLaboratoryValidationRules,
)

_COLUMNS = tuple(field.name for field in fields(NHCLaboratoryTestRecord))
_POST_INSERT_SQL = (
    """
    INSERT INTO laboratory_test_fts(rowid, name, analyte, category_name)
    SELECT rowid, name, analyte, category_name FROM laboratory_test ORDER BY code
    """,
    """
    WITH RECURSIVE grams(code, text, position) AS (
        SELECT code, name, 1 FROM laboratory_test WHERE length(name) >= 2
        UNION ALL
        SELECT code, text, position + 1 FROM grams WHERE position < length(text) - 1
    )
    INSERT OR IGNORE INTO laboratory_test_search_bigram(term, code)
    SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2
    """,
    "INSERT INTO laboratory_test_fts(laboratory_test_fts) VALUES('optimize')",
)


def build_nhc_laboratory_sqlite(
    records: Iterable[NHCLaboratoryTestRecord],
    rules: NHCLaboratoryValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact[NHCLaboratoryValidationReport]:
    return build_sqlite_artifact(
        records,
        NHCLaboratoryRecordValidator(rules),
        astuple,
        _COLUMNS,
        schema_path,
        output_path,
        table="laboratory_test",
        staging_table="laboratory_test_staging",
        post_insert_sql=_POST_INSERT_SQL,
    )
