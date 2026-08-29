"""SQLite artifact construction for NHSA drug records."""

from collections.abc import Iterable
from dataclasses import astuple, fields
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact as CoreSQLiteArtifact
from cn_health_compiler.core.sqlite import build_sqlite_artifact
from cn_health_compiler.sources.nhsa_drugs.records import DrugRecord
from cn_health_compiler.sources.nhsa_drugs.validation import (
    DrugRecordValidator,
    DrugValidationRules,
    ValidationReport,
)

_COLUMNS = tuple(field.name for field in fields(DrugRecord))
_POST_INSERT_SQL = (
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
    """,
    "INSERT INTO drug_fts(drug_fts) VALUES('optimize')",
)

type SQLiteArtifact = CoreSQLiteArtifact[ValidationReport]


def build_drug_sqlite(
    records: Iterable[DrugRecord],
    rules: DrugValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact:
    return build_sqlite_artifact(
        records,
        DrugRecordValidator(rules),
        astuple,
        _COLUMNS,
        schema_path,
        output_path,
        table="drug",
        staging_table="drug_staging",
        post_insert_sql=_POST_INSERT_SQL,
    )
