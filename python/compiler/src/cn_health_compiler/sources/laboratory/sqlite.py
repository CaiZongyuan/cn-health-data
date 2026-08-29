"""SQLite artifact construction for the curated laboratory catalog."""

from collections.abc import Iterable
from dataclasses import astuple, fields
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_artifact
from cn_health_compiler.sources.laboratory.records import LaboratoryConceptRecord
from cn_health_compiler.sources.laboratory.validation import (
    LaboratoryRecordValidator,
    LaboratoryValidationReport,
    LaboratoryValidationRules,
)

_COLUMNS = tuple(field.name for field in fields(LaboratoryConceptRecord))
_POST_INSERT_SQL = (
    """
    INSERT INTO laboratory_concept_fts(rowid, display_zh)
    SELECT rowid, display_zh FROM laboratory_concept ORDER BY code
    """,
    """
    WITH RECURSIVE grams(code, text, position) AS (
        SELECT code, display_zh, 1 FROM laboratory_concept WHERE length(display_zh) >= 2
        UNION ALL
        SELECT code, text, position + 1
        FROM grams
        WHERE position < length(text) - 1
    )
    INSERT OR IGNORE INTO laboratory_concept_search_bigram(term, code)
    SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2
    """,
    "INSERT INTO laboratory_concept_fts(laboratory_concept_fts) VALUES('optimize')",
)


def build_laboratory_sqlite(
    records: Iterable[LaboratoryConceptRecord],
    rules: LaboratoryValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact[LaboratoryValidationReport]:
    return build_sqlite_artifact(
        records,
        LaboratoryRecordValidator(rules),
        astuple,
        _COLUMNS,
        schema_path,
        output_path,
        table="laboratory_concept",
        staging_table="laboratory_concept_staging",
        post_insert_sql=_POST_INSERT_SQL,
    )
