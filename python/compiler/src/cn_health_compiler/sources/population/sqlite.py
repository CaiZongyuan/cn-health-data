"""Deterministic SQLite builder for Chinese aggregate population data."""

from collections.abc import Iterable
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_artifact
from cn_health_compiler.sources.population.records import PopulationAgeSexRecord
from cn_health_compiler.sources.population.validation import (
    PopulationRecordValidator,
    PopulationValidationReport,
    PopulationValidationRules,
)

_COLUMNS = (
    "code",
    "country_code",
    "variant",
    "year",
    "mid_period",
    "age_group",
    "age_start",
    "age_end",
    "male_population",
    "female_population",
    "total_population",
    "source_row",
    "source_version",
    "source_sha256",
)


def _row_values(record: PopulationAgeSexRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.country_code,
        record.variant,
        record.year,
        record.mid_period,
        record.age_group,
        record.age_start,
        record.age_end,
        record.male_population,
        record.female_population,
        record.total_population,
        record.source_row,
        record.source_version,
        record.source_sha256,
    )


def build_population_sqlite(
    records: Iterable[PopulationAgeSexRecord],
    rules: PopulationValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact[PopulationValidationReport]:
    return build_sqlite_artifact(
        records,
        PopulationRecordValidator(rules),
        _row_values,
        _COLUMNS,
        schema_path,
        output_path,
        table="population_age_sex",
        staging_table="population_age_sex_staging",
        post_insert_sql=(),
    )
