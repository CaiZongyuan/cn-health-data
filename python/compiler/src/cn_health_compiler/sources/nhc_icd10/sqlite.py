"""SQLite artifact construction for NHC clinical diagnosis records."""

from collections.abc import Iterable
from dataclasses import astuple, fields
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact as CoreSQLiteArtifact
from cn_health_compiler.core.sqlite import build_sqlite_artifact
from cn_health_compiler.sources.nhc_icd10.records import DiagnosisRecord
from cn_health_compiler.sources.nhc_icd10.validation import (
    DiagnosisRecordValidator,
    DiagnosisValidationReport,
    DiagnosisValidationRules,
)

_COLUMNS = tuple(field.name for field in fields(DiagnosisRecord))
_POST_INSERT_SQL = (
    "INSERT INTO diagnosis_fts(rowid, name) SELECT rowid, name FROM diagnosis ORDER BY code",
    "INSERT INTO diagnosis_fts(diagnosis_fts) VALUES('optimize')",
)

type DiagnosisSQLiteArtifact = CoreSQLiteArtifact[DiagnosisValidationReport]


def build_diagnosis_sqlite(
    records: Iterable[DiagnosisRecord],
    rules: DiagnosisValidationRules,
    schema_path: Path,
    output_path: Path,
) -> DiagnosisSQLiteArtifact:
    return build_sqlite_artifact(
        records,
        DiagnosisRecordValidator(rules),
        astuple,
        _COLUMNS,
        schema_path,
        output_path,
        table="diagnosis",
        staging_table="diagnosis_staging",
        post_insert_sql=_POST_INSERT_SQL,
    )
