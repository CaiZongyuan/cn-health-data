"""Deterministic SQLite builder for Chinese name components."""

from collections.abc import Iterable
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_artifact
from cn_health_compiler.sources.names.records import NameComponentRecord
from cn_health_compiler.sources.names.validation import (
    NamesRecordValidator,
    NamesValidationReport,
    NamesValidationRules,
)

_COLUMNS = (
    "code",
    "kind",
    "gender",
    "text",
    "weight",
    "is_compound",
    "source_duplicate",
    "source_line",
    "source_ordinal",
    "source_version",
    "source_sha256",
)


def _row_values(record: NameComponentRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.kind,
        record.gender,
        record.text,
        record.weight,
        record.is_compound,
        record.source_duplicate,
        record.source_line,
        record.source_ordinal,
        record.source_version,
        record.source_sha256,
    )


def build_names_sqlite(
    records: Iterable[NameComponentRecord],
    rules: NamesValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact[NamesValidationReport]:
    return build_sqlite_artifact(
        records,
        NamesRecordValidator(rules),
        _row_values,
        _COLUMNS,
        schema_path,
        output_path,
        table="name_component",
        staging_table="name_component_staging",
        post_insert_sql=(),
    )
